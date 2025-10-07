'''
Purpose: Simplified application for nominating and voting on books.
'''
# Standard modules
import streamlit as st
from dataclasses import dataclass
from typing import List, Dict
import polars as pl
import requests
from urllib.parse import quote
import plotly.graph_objects as go

def get_api_key():
    """Get Google Books API key from local file or Streamlit secrets"""
    try:
        from key import GOOGLE_BOOKS_API_KEY
        return GOOGLE_BOOKS_API_KEY
    except ImportError:
        # Try Streamlit secrets (works in deployed environment)
        try:
            return st.secrets.get('GOOGLE_BOOKS_API_KEY', None)
        except (AttributeError, FileNotFoundError):
            return None

@dataclass
class Book:
    """Represents a book nomination"""
    title: str
    author: str
    description: str
    genre: str
    page_count: int
    id: str = None

    def __post_init__(self):
        if self.id is None:
            self.id = f"{self.title}_{self.author}".replace(" ", "_").lower()

def search_book_metadata(title: str, author: str = "") -> List[Dict]:
    """Search for book metadata using Google Books API, returns up to 10 results"""
    try:
        # Get API key
        api_key = get_api_key()

        # Construct search query
        query = title
        if author:
            query += f" inauthor:{author}"

        url = f"https://www.googleapis.com/books/v1/volumes?q={quote(query)}&maxResults=10"

        # Add API key if available (optional, helps avoid rate limits)
        if api_key:
            url += f"&key={api_key}"

        # Set headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('totalItems', 0) > 0:
                results = []
                for idx, item in enumerate(data.get('items', [])):
                    book_info = item.get('volumeInfo', {})

                    # Extract metadata with unique ID
                    metadata = {
                        'id': item.get('id', f'book_{idx}'),  # Use Google Books ID or fallback
                        'title': book_info.get('title', title),
                        'author': ', '.join(book_info.get('authors', [])) if book_info.get('authors') else '',
                        'description': book_info.get('description', ''),
                        'genre': ', '.join(book_info.get('categories', [])) if book_info.get('categories') else '',
                        'page_count': book_info.get('pageCount', 0)
                    }
                    results.append(metadata)
                return results
            else:
                st.warning("No books found matching your search. Please try different keywords or enter metadata manually.")
        else:
            if response.status_code == 403:
                if api_key:
                    st.error("⚠️ Google Books API access denied (403). Your API key may be invalid or has exceeded quota. Please check your API key configuration.")
                else:
                    st.error("⚠️ Google Books API access denied (403). No API key detected. To fix this:\n\n"
                           "**Local development:** Create a file `src/stl_book_club_v2/key.py` with:\n"
                           "```python\n"
                           "GOOGLE_BOOKS_API_KEY = 'your-api-key-here'\n"
                           "```\n\n"
                           "**Streamlit Cloud:** Add `GOOGLE_BOOKS_API_KEY` to your app secrets.\n\n"
                           "Get a free API key at: https://console.cloud.google.com/apis/credentials")
            else:
                st.error(f"Google Books API returned status code {response.status_code}. Please try again or enter metadata manually.")
    except requests.exceptions.Timeout:
        st.error("Search request timed out. Please check your internet connection and try again.")
    except requests.exceptions.RequestException as e:
        st.error(f"Network error while searching: {str(e)}. Please check your internet connection.")
    except Exception as e:
        st.error(f"Unexpected error fetching book data: {type(e).__name__}: {str(e)}")

    return []

@st.cache_resource
def get_persistent_storage():
    """Create a persistent storage dictionary that survives across sessions"""
    return {
        'books': [],
        'votes': {}
    }

def initialize_session_state():
    """Initialize session state variables"""
    # Get persistent storage
    storage = get_persistent_storage()

    # Initialize session state with data from persistent storage
    if 'books' not in st.session_state:
        st.session_state.books = storage['books']
    if 'votes' not in st.session_state:
        st.session_state.votes = storage['votes']
    if 'voting_complete' not in st.session_state:
        st.session_state.voting_complete = False
    if 'show_results' not in st.session_state:
        st.session_state.show_results = False
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    if 'selected_book' not in st.session_state:
        st.session_state.selected_book = None

    # Sync session state back to persistent storage
    storage['books'] = st.session_state.books
    storage['votes'] = st.session_state.votes

def add_book(book: Book):
    """Add a book to the nomination list"""
    storage = get_persistent_storage()

    # Check for duplicates
    for existing_book in st.session_state.books:
        if existing_book.id == book.id:
            return False
    st.session_state.books.append(book)

    # Sync to persistent storage
    storage['books'] = st.session_state.books
    return True

def remove_book(book_id: str):
    """Remove a book from the nomination list"""
    storage = get_persistent_storage()

    st.session_state.books = [b for b in st.session_state.books if b.id != book_id]
    # Also remove any votes for this book
    for voter in st.session_state.votes:
        st.session_state.votes[voter] = [b_id for b_id in st.session_state.votes[voter] if b_id != book_id]

    # Sync to persistent storage
    storage['books'] = st.session_state.books
    storage['votes'] = st.session_state.votes

def calculate_ranked_choice_winner(votes: Dict[str, List[str]], books: List[Book]) -> List[Dict]:
    """
    Calculate ranked choice voting results
    Returns a list of rounds with vote counts and eliminated book
    """
    if not votes or not books:
        return []

    # Create a set of book IDs that have at least one vote
    all_voted_book_ids = set()
    for ranked_choices in votes.values():
        all_voted_book_ids.update(ranked_choices)

    # Only include books that have votes
    active_book_ids = {book.id for book in books if book.id in all_voted_book_ids}

    if not active_book_ids:
        return []

    rounds = []

    while len(active_book_ids) > 1:
        # Count first-choice votes for active books
        vote_counts = {}

        # Initialize all active books with 0 votes
        for book_id in active_book_ids:
            vote_counts[book_id] = 0

        # Count votes
        for ranked_choices in votes.values():
            # Find the first choice that's still active
            for book_id in ranked_choices:
                if book_id in active_book_ids:
                    vote_counts[book_id] += 1
                    break

        # Check if any book has more than 50% of votes (majority winner)
        total_votes = len(votes)
        majority_threshold = total_votes / 2
        majority_winner = None

        for book_id, count in vote_counts.items():
            if count > majority_threshold:
                majority_winner = book_id
                break

        # If there's a majority winner, declare them and end
        if majority_winner:
            round_data = {
                'round_number': len(rounds) + 1,
                'vote_counts': dict(vote_counts),
                'active_books': len(active_book_ids),
                'eliminated': None,
                'winner': majority_winner,
                'majority_win': True
            }
            rounds.append(round_data)
            break

        # Record this round
        round_data = {
            'round_number': len(rounds) + 1,
            'vote_counts': dict(vote_counts),
            'active_books': len(active_book_ids),
            'eliminated': None
        }

        # Find books with fewest votes
        min_votes = min(vote_counts.values())
        # Get all books with minimum votes (could be multiple tied books)
        books_with_min_votes = [book_id for book_id, count in vote_counts.items() if count == min_votes]

        # If there's a tie, use next-rank tiebreaker to eliminate only ONE book
        if len(books_with_min_votes) > 1:
            # Count next-choice votes for tied books
            next_choice_counts = {book_id: 0 for book_id in books_with_min_votes}

            for ranked_choices in votes.values():
                # Find first active choice
                first_choice_idx = -1
                for idx, book_id in enumerate(ranked_choices):
                    if book_id in active_book_ids:
                        first_choice_idx = idx
                        break

                if first_choice_idx >= 0:
                    # If ALL books are tied (all have same first-choice votes),
                    # OR if this voter's first choice is among the tied books,
                    # look at their next preference among the tied books
                    if len(books_with_min_votes) == len(active_book_ids) or ranked_choices[first_choice_idx] in books_with_min_votes:
                        # Look for next choice among tied books (after their current first choice)
                        for idx in range(first_choice_idx + 1, len(ranked_choices)):
                            if ranked_choices[idx] in books_with_min_votes:
                                next_choice_counts[ranked_choices[idx]] += 1
                                break
                    else:
                        # First choice is not one of the tied books, look for any choice among tied books
                        for idx in range(first_choice_idx + 1, len(ranked_choices)):
                            if ranked_choices[idx] in books_with_min_votes:
                                next_choice_counts[ranked_choices[idx]] += 1
                                break

            # If we have next choice data, find book with fewest next choices
            if any(count > 0 for count in next_choice_counts.values()):
                min_next_choice = min(next_choice_counts.values())
                books_with_min_votes = [book_id for book_id, count in next_choice_counts.items()
                                       if count == min_next_choice]

        # Check if all remaining books are tied (even after tiebreaker)
        if len(books_with_min_votes) == len(active_book_ids):
            # All books tied - eliminate first one and declare second as winner
            eliminated_book_id = books_with_min_votes[0]
            winner_id = books_with_min_votes[1]
            active_book_ids.remove(eliminated_book_id)
            round_data['eliminated'] = eliminated_book_id
            rounds.append(round_data)

            # Add final round with winner - all votes go to the remaining candidate
            total_votes = len(votes)
            rounds.append({
                'round_number': len(rounds) + 1,
                'vote_counts': {winner_id: total_votes},
                'active_books': 1,
                'eliminated': None,
                'winner': winner_id
            })
            # Clear active_book_ids to prevent duplicate winner round
            active_book_ids.clear()
            break
        else:
            # Eliminate only ONE book - if still tied after tiebreaker, pick first one
            eliminated_book_id = books_with_min_votes[0]
            active_book_ids.remove(eliminated_book_id)
            round_data['eliminated'] = eliminated_book_id

        rounds.append(round_data)

    # Final round - the winner (only if we didn't already declare winner above)
    if active_book_ids and len(active_book_ids) == 1:
        winner_id = list(active_book_ids)[0]

        # All remaining votes go to the last remaining candidate
        total_votes = len(votes)
        vote_counts = {winner_id: total_votes}

        rounds.append({
            'round_number': len(rounds) + 1,
            'vote_counts': dict(vote_counts),
            'active_books': 1,
            'eliminated': None,
            'winner': winner_id
        })

    return rounds

def display_book_card(book: Book, show_remove=False):
    """Display a book in a nice card format"""
    with st.container():
        st.markdown(f"### 📚 {book.title}")
        st.markdown(f"**Author:** {book.author}")
        st.markdown(f"**Genre:** {book.genre} | **Pages:** {book.page_count}")
        st.markdown(f"*{book.description}*")
        if show_remove:
            if st.button(f"Remove", key=f"remove_{book.id}"):
                remove_book(book.id)
                st.rerun()
        st.divider()

def display_voting_results(rounds: List[Dict], books: List[Book], total_votes: int):
    """Display voting results with nice visualization"""
    st.header("🏆 Voting Results")

    # Display total votes
    st.info(f"**Total Votes Cast:** {total_votes}")

    # Create a lookup for book titles
    book_lookup = {book.id: book.title for book in books}

    # Find and display the winner at the top
    winner_round = None
    for round_data in rounds:
        if 'winner' in round_data:
            winner_round = round_data
            break

    if winner_round:
        winner_title = book_lookup.get(winner_round['winner'], 'Unknown')
        st.success(f"## 🎉 Winner: {winner_title}")
        st.divider()

    # Create line chart data for all rounds
    st.subheader("📈 Vote Progression Across Rounds")

    # Collect all unique books across all rounds
    all_books = set()
    for round_data in rounds:
        all_books.update(round_data['vote_counts'].keys())

    # Track which books were eliminated and in which round, and find winner
    eliminated_books = {}
    winner_info = None
    for round_data in rounds:
        if round_data.get('eliminated'):
            eliminated = round_data['eliminated']
            # Handle both single book and multiple books elimination
            if isinstance(eliminated, list):
                for book_id in eliminated:
                    eliminated_books[book_id] = round_data['round_number']
            else:
                eliminated_books[eliminated] = round_data['round_number']

        # Track winner
        if round_data.get('winner'):
            winner_info = {
                'book_id': round_data['winner'],
                'round': round_data['round_number'],
                'votes': round_data['vote_counts'].get(round_data['winner'], 0)
            }

    # Build data for line chart using Plotly
    fig = go.Figure()

    for book_id in all_books:
        book_title = book_lookup.get(book_id, book_id)
        x_values = []
        y_values = []

        # Collect vote data for this book across rounds
        for round_data in rounds:
            if book_id in round_data['vote_counts']:
                x_values.append(round_data['round_number'])
                y_values.append(round_data['vote_counts'][book_id])

        # If book was eliminated, add a point going down to zero
        if book_id in eliminated_books:
            elim_round = eliminated_books[book_id]
            # Add one more point after elimination at zero
            x_values.append(elim_round + 0.5)
            y_values.append(0)

        # Add line trace
        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines+markers',
            name=book_title,
            line=dict(width=3),
            marker=dict(size=8)
        ))

        # Add bomb emoji marker if this book was eliminated
        if book_id in eliminated_books:
            elim_round = eliminated_books[book_id]
            elim_votes = rounds[elim_round - 1]['vote_counts'].get(book_id, 0)

            fig.add_trace(go.Scatter(
                x=[elim_round],
                y=[elim_votes],
                mode='text',
                text=['💣'],
                textfont=dict(size=20),
                showlegend=False,
                hoverinfo='skip'
            ))

    # Add trophy emoji marker for the winner
    if winner_info:
        fig.add_trace(go.Scatter(
            x=[winner_info['round']],
            y=[winner_info['votes']],
            mode='text',
            text=['🏆'],
            textfont=dict(size=24),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Update layout for integer axes
    fig.update_layout(
        xaxis=dict(
            title='Round',
            dtick=1,  # Show every integer
            tickmode='linear'
        ),
        yaxis=dict(
            title='Votes',
            dtick=1,  # Show every integer
            tickmode='linear',
            rangemode='tozero'  # Start y-axis at 0
        ),
        hovermode='x unified',
        height=500
    )

    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Display individual round details (tables only, no bar charts)
    st.subheader("📊 Round-by-Round Results")

    for round_data in rounds:
        round_num = round_data['round_number']

        # Check if this is the final round
        is_final = 'winner' in round_data

        # Display header for all rounds including final
        if is_final:
            st.subheader(f"Round {round_num} - Final")
        else:
            st.subheader(f"Round {round_num}")

        # Create a DataFrame for visualization with percentages
        vote_data = []
        total_votes = sum(round_data['vote_counts'].values())

        for book_id, count in round_data['vote_counts'].items():
            percentage = round((count / total_votes * 100)) if total_votes > 0 else 0
            vote_data.append({
                'Book': book_lookup.get(book_id, book_id),
                'Votes': count,
                'Percentage': f"{percentage}%"
            })

        if vote_data:
            df = pl.DataFrame(vote_data).sort('Votes', descending=True)

            # Display table
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Show eliminated book(s) or winner
        if is_final:
            # Show winner message is already at top, just show final tally
            pass
        elif round_data['eliminated']:
            eliminated = round_data['eliminated']
            # Handle both single book and multiple books elimination
            if isinstance(eliminated, list):
                eliminated_titles = [book_lookup.get(book_id, book_id) for book_id in eliminated]
                st.warning(f"❌ Eliminated: **{', '.join(eliminated_titles)}**")
            else:
                eliminated_title = book_lookup.get(eliminated, 'Unknown')
                st.warning(f"❌ Eliminated: **{eliminated_title}**")

        st.divider()

    # Display winning book details at bottom
    if winner_round:
        st.divider()
        winner_title = book_lookup.get(winner_round['winner'], 'Unknown')
        winner_book = next((book for book in books if book.id == winner_round['winner']), None)

        st.success(f"## 🎉 Winner: {winner_title}")

        if winner_book:
            with st.container():
                col1, col2 = st.columns([1, 2])

                with col1:
                    st.markdown(f"### 📚 {winner_book.title}")
                    st.markdown(f"**Author:** {winner_book.author}")
                    st.markdown(f"**Genre:** {winner_book.genre}")
                    st.markdown(f"**Pages:** {winner_book.page_count}")

                with col2:
                    st.markdown("**Description:**")
                    st.markdown(f"*{winner_book.description}*")

                # Show if it was a majority win
                if winner_round.get('majority_win'):
                    total_votes = sum(winner_round['vote_counts'].values())
                    winner_votes = winner_round['vote_counts'].get(winner_round['winner'], 0)
                    percentage = (winner_votes / total_votes * 100) if total_votes > 0 else 0
                    st.info(f"🎯 Won by majority with {winner_votes}/{total_votes} votes ({percentage:.1f}%) in Round {winner_round['round_number']}")

def main():
    st.set_page_config(page_title="Book Club Voting", page_icon="📚", layout="wide")
    initialize_session_state()

    st.title("📚 Book Club: Nominations & Voting")

    # Create tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Nominate Books", "📋 View Nominations", "🗳️ Vote", "📊 Results", "🐛 Debug"])

    # Tab 1: Nominate Books
    with tab1:
        st.header("Nominate a Book")

        # Search section
        st.subheader("🔍 Search for Book")
        search_col1, search_col2 = st.columns([3, 1])

        with search_col1:
            search_title = st.text_input("Search by Title", placeholder="Enter book title to search", key="search_title")
        with search_col2:
            search_author = st.text_input("Author (optional)", placeholder="Author name", key="search_author")

        if st.button("🔎 Search Online", use_container_width=True):
            if search_title:
                with st.spinner("Searching for books..."):
                    results = search_book_metadata(search_title, search_author)
                    if results:
                        st.session_state.search_results = results
                        # Auto-populate first result
                        st.session_state.selected_book = results[0] if results else None
                        st.success(f"✅ Found {len(results)} result(s)! First result selected.")
                        st.rerun()
                    else:
                        st.warning("No results found. Please enter metadata manually.")
                        st.session_state.search_results = []
                        st.session_state.selected_book = None
            else:
                st.error("Please enter a book title to search")

        st.divider()
        st.subheader("📝 Book Details")

        # Display currently selected book if available
        if st.session_state.selected_book:
            st.info(f"📖 Currently Selected: **{st.session_state.selected_book.get('title', 'N/A')}** by {st.session_state.selected_book.get('author', 'N/A')}")

        # Pre-fill with selected book if available
        default_title = st.session_state.selected_book.get('title', '') if st.session_state.selected_book else ''
        default_author = st.session_state.selected_book.get('author', '') if st.session_state.selected_book else ''
        default_genre = st.session_state.selected_book.get('genre', '') if st.session_state.selected_book else ''
        default_description = st.session_state.selected_book.get('description', '') if st.session_state.selected_book else ''
        default_pages = st.session_state.selected_book.get('page_count', 300) if st.session_state.selected_book else 300

        with st.form("book_nomination_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                title = st.text_input("Book Title*", value=default_title, placeholder="Enter book title")
                author = st.text_input("Author*", value=default_author, placeholder="Enter author name")
                genre = st.text_input("Genre*", value=default_genre, placeholder="e.g., Fiction, Mystery, Science Fiction")

            with col2:
                page_count = st.number_input("Page Count*", min_value=1, value=max(1, default_pages), step=1)
                description = st.text_area("Description*", value=default_description, placeholder="Brief description of the book", height=100)

            submit = st.form_submit_button("Add Book", use_container_width=True)

            if submit:
                if title and author and genre and description:
                    book = Book(
                        title=title,
                        author=author,
                        description=description,
                        genre=genre,
                        page_count=page_count
                    )
                    if add_book(book):
                        st.success(f"✅ Added '{title}' by {author}!")
                        # Clear search results after adding
                        st.session_state.search_results = []
                        st.session_state.selected_book = None
                        st.rerun()
                    else:
                        st.error("This book has already been nominated!")
                else:
                    st.error("Please fill in all fields!")

        # Display search results if available (below the form)
        if st.session_state.search_results:
            st.divider()
            st.subheader("📚 Search Results")
            st.caption("Click on a book to select it")

            for idx, result in enumerate(st.session_state.search_results):
                # Check if this is the selected book using unique ID
                is_selected = (st.session_state.selected_book and
                             result.get('id') == st.session_state.selected_book.get('id'))

                with st.container():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        # Highlight selected book with checkmark
                        if is_selected:
                            st.markdown(f"✅ **{result['title']}**")
                        else:
                            st.markdown(f"**{result['title']}**")
                        if result['author']:
                            st.caption(f"by {result['author']}")
                    with col2:
                        if st.button("Select", key=f"select_{idx}", type="primary" if is_selected else "secondary"):
                            st.session_state.selected_book = result
                            st.rerun()
                    st.divider()

    # Tab 2: View Nominations
    with tab2:
        st.header("Nominated Books")

        if st.session_state.books:
            st.info(f"Total nominations: {len(st.session_state.books)}")

            for book in st.session_state.books:
                display_book_card(book, show_remove=True)
        else:
            st.info("No books nominated yet. Go to the 'Nominate Books' tab to add some!")

    # Tab 3: Vote
    with tab3:
        st.header("Cast Your Vote")

        if len(st.session_state.books) < 2:
            st.warning("Need at least 2 books to start voting!")
        else:
            voter_name = st.text_input("Your Name", placeholder="Enter your name")

            if voter_name:
                st.subheader("Rank the books in order of preference")
                st.caption("Drag and drop to reorder, or use the select boxes")

                # Create a list of book options
                book_options = {f"{book.title} by {book.author}": book.id
                               for book in st.session_state.books}

                # Get current vote if exists
                current_vote = st.session_state.votes.get(voter_name, [])

                # Create ranking interface
                rankings = []
                for i in range(len(st.session_state.books)):
                    # Pre-select if vote exists
                    default_index = 0
                    if i < len(current_vote):
                        for idx, (_, book_id) in enumerate(book_options.items()):
                            if book_id == current_vote[i]:
                                default_index = idx
                                break

                    choice = st.selectbox(
                        f"Choice #{i+1}",
                        options=list(book_options.keys()),
                        key=f"rank_{i}",
                        index=default_index
                    )
                    rankings.append(book_options[choice])

                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("Submit Vote", type="primary", use_container_width=True):
                        # Check for duplicates in rankings
                        if len(rankings) != len(set(rankings)):
                            st.error("Please rank each book only once!")
                        else:
                            st.session_state.votes[voter_name] = rankings
                            # Sync to persistent storage
                            storage = get_persistent_storage()
                            storage['votes'] = st.session_state.votes
                            st.success(f"✅ Vote recorded for {voter_name}!")
                            st.balloons()

                with col2:
                    if voter_name in st.session_state.votes:
                        if st.button("Remove My Vote", use_container_width=True):
                            del st.session_state.votes[voter_name]
                            # Sync to persistent storage
                            storage = get_persistent_storage()
                            storage['votes'] = st.session_state.votes
                            st.rerun()
            else:
                st.info("👆 Enter your name to start voting")

            # Show current votes
            if st.session_state.votes:
                st.divider()
                st.subheader("Current Voters")
                st.write(f"**{len(st.session_state.votes)} vote(s) cast:** {', '.join(st.session_state.votes.keys())}")

    # Tab 4: Results
    with tab4:
        st.header("Voting Results")

        if len(st.session_state.votes) == 0:
            st.info("No votes cast yet!")
        elif len(st.session_state.books) < 2:
            st.warning("Need at least 2 books to calculate results!")
        else:
            if st.button("🔄 Calculate Results", type="primary"):
                st.session_state.show_results = True

            if st.session_state.show_results:
                rounds = calculate_ranked_choice_winner(
                    st.session_state.votes,
                    st.session_state.books
                )

                if rounds:
                    display_voting_results(rounds, st.session_state.books, len(st.session_state.votes))
                else:
                    st.error("Unable to calculate results")

                if st.button("Hide Results"):
                    st.session_state.show_results = False
                    st.rerun()

    # Tab 5: Debug
    with tab5:
        st.header("🐛 Debug - Current Votes")

        # Password protection
        if 'debug_authenticated' not in st.session_state:
            st.session_state.debug_authenticated = False

        if not st.session_state.debug_authenticated:
            password = st.text_input("Enter password to access debug data:", type="password", key="debug_password")
            if st.button("Submit", key="debug_submit"):
                if password == "hyrule":
                    st.session_state.debug_authenticated = True
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
        else:
            # Show logout button
            if st.button("🔒 Lock Debug Tab"):
                st.session_state.debug_authenticated = False
                st.rerun()

            st.divider()

            if not st.session_state.votes:
                st.info("No votes have been cast yet.")
            else:
                st.subheader(f"Total Voters: {len(st.session_state.votes)}")

                # Create a lookup for book titles
                book_lookup = {book.id: book.title for book in st.session_state.books}

                # Display votes in a table format
                for voter_name, rankings in st.session_state.votes.items():
                    st.markdown(f"### 👤 {voter_name}")

                    # Create ranked list
                    vote_data = []
                    for rank, book_id in enumerate(rankings, 1):
                        book_title = book_lookup.get(book_id, f"Unknown ({book_id})")
                        vote_data.append({
                            'Rank': rank,
                            'Book': book_title
                        })

                    if vote_data:
                        df = pl.DataFrame(vote_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)

                    st.divider()

                # Show raw data in expander
                with st.expander("📋 View Raw Vote Data"):
                    st.json(st.session_state.votes)

                # Show persistent storage status
                st.divider()
                st.subheader("💾 Persistent Storage")
                storage = get_persistent_storage()
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Books in Storage", len(storage['books']))
                with col2:
                    st.metric("Votes in Storage", len(storage['votes']))

if __name__ == '__main__':
    main()

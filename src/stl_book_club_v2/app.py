'''
Purpose: Simplified application for nominating and voting on books.
'''
# Standard modules
import streamlit as st
from dataclasses import dataclass
from typing import List, Dict, Optional
import polars as pl
import requests
from urllib.parse import quote

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

def search_book_metadata(title: str, author: str = "") -> Optional[Dict]:
    """Search for book metadata using Google Books API"""
    try:
        # Construct search query
        query = title
        if author:
            query += f" inauthor:{author}"

        url = f"https://www.googleapis.com/books/v1/volumes?q={quote(query)}&maxResults=1"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('totalItems', 0) > 0:
                book_info = data['items'][0]['volumeInfo']

                # Extract metadata
                metadata = {
                    'title': book_info.get('title', title),
                    'author': ', '.join(book_info.get('authors', [author])) if book_info.get('authors') else author,
                    'description': book_info.get('description', ''),
                    'genre': ', '.join(book_info.get('categories', [])) if book_info.get('categories') else '',
                    'page_count': book_info.get('pageCount', 0)
                }
                return metadata
    except Exception as e:
        st.error(f"Error fetching book data: {str(e)}")

    return None

def initialize_session_state():
    """Initialize session state variables"""
    if 'books' not in st.session_state:
        st.session_state.books = []
    if 'votes' not in st.session_state:
        st.session_state.votes = {}
    if 'voting_complete' not in st.session_state:
        st.session_state.voting_complete = False
    if 'show_results' not in st.session_state:
        st.session_state.show_results = False
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None

def add_book(book: Book):
    """Add a book to the nomination list"""
    # Check for duplicates
    for existing_book in st.session_state.books:
        if existing_book.id == book.id:
            return False
    st.session_state.books.append(book)
    return True

def remove_book(book_id: str):
    """Remove a book from the nomination list"""
    st.session_state.books = [b for b in st.session_state.books if b.id != book_id]
    # Also remove any votes for this book
    for voter in st.session_state.votes:
        st.session_state.votes[voter] = [b_id for b_id in st.session_state.votes[voter] if b_id != book_id]

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

        # Record this round
        round_data = {
            'round_number': len(rounds) + 1,
            'vote_counts': dict(vote_counts),
            'active_books': len(active_book_ids),
            'eliminated': None
        }

        # Find book with fewest votes
        min_votes = min(vote_counts.values())
        # Get all books with minimum votes
        books_with_min_votes = [book_id for book_id, count in vote_counts.items() if count == min_votes]

        # Check if we're down to 2 books and they're tied
        if len(active_book_ids) == 2 and len(books_with_min_votes) == 2:
            # Both books have same votes - eliminate one and declare winner
            eliminated_book_id = books_with_min_votes[0]
            winner_id = books_with_min_votes[1]
            active_book_ids.remove(eliminated_book_id)
            round_data['eliminated'] = eliminated_book_id
            rounds.append(round_data)

            # Add final round with winner
            rounds.append({
                'round_number': len(rounds) + 1,
                'vote_counts': {winner_id: vote_counts[winner_id]},
                'active_books': 1,
                'eliminated': None,
                'winner': winner_id
            })
            # Clear active_book_ids to prevent duplicate winner round
            active_book_ids.clear()
            break
        else:
            # Normal elimination
            eliminated_book_id = books_with_min_votes[0]
            active_book_ids.remove(eliminated_book_id)
            round_data['eliminated'] = eliminated_book_id

        rounds.append(round_data)

    # Final round - the winner (only if we didn't already declare winner above)
    if active_book_ids and len(active_book_ids) == 1:
        winner_id = list(active_book_ids)[0]
        vote_counts = {}
        vote_counts[winner_id] = 0
        for ranked_choices in votes.values():
            for book_id in ranked_choices:
                if book_id == winner_id:
                    vote_counts[book_id] += 1
                    break

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

def display_voting_results(rounds: List[Dict], books: List[Book]):
    """Display voting results with nice visualization"""
    st.header("🏆 Voting Results")

    # Create a lookup for book titles
    book_lookup = {book.id: book.title for book in books}

    for round_data in rounds:
        round_num = round_data['round_number']

        # Check if this is the final round
        is_final = 'winner' in round_data

        if is_final:
            st.success(f"### 🎉 Winner: {book_lookup.get(round_data['winner'], 'Unknown')}")
        else:
            st.subheader(f"Round {round_num}")

        # Create a DataFrame for visualization
        vote_data = []
        for book_id, count in round_data['vote_counts'].items():
            vote_data.append({
                'Book': book_lookup.get(book_id, book_id),
                'Votes': count
            })

        if vote_data:
            df = pl.DataFrame(vote_data).sort('Votes', descending=True)

            # Display bar chart
            st.bar_chart(df.to_pandas().set_index('Book'))

            # Display table
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Show eliminated book
        if round_data['eliminated']:
            eliminated_title = book_lookup.get(round_data['eliminated'], 'Unknown')
            st.warning(f"❌ Eliminated: **{eliminated_title}**")

        if not is_final:
            st.divider()

def main():
    st.set_page_config(page_title="Book Club Voting", page_icon="📚", layout="wide")
    initialize_session_state()

    st.title("📚 Book Club: Nominations & Voting")

    # Create tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Nominate Books", "📋 View Nominations", "🗳️ Vote", "📊 Results"])

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
                with st.spinner("Searching for book..."):
                    metadata = search_book_metadata(search_title, search_author)
                    if metadata:
                        st.session_state.search_results = metadata
                        st.success("✅ Book found! Metadata loaded below.")
                        st.rerun()
                    else:
                        st.warning("No results found. Please enter metadata manually.")
                        st.session_state.search_results = None
            else:
                st.error("Please enter a book title to search")

        st.divider()
        st.subheader("📝 Book Details")

        # Pre-fill with search results if available
        default_title = st.session_state.search_results.get('title', '') if st.session_state.search_results else ''
        default_author = st.session_state.search_results.get('author', '') if st.session_state.search_results else ''
        default_genre = st.session_state.search_results.get('genre', '') if st.session_state.search_results else ''
        default_description = st.session_state.search_results.get('description', '') if st.session_state.search_results else ''
        default_pages = st.session_state.search_results.get('page_count', 300) if st.session_state.search_results else 300

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
                        st.session_state.search_results = None
                        st.rerun()
                    else:
                        st.error("This book has already been nominated!")
                else:
                    st.error("Please fill in all fields!")

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
                            st.success(f"✅ Vote recorded for {voter_name}!")
                            st.balloons()

                with col2:
                    if voter_name in st.session_state.votes:
                        if st.button("Remove My Vote", use_container_width=True):
                            del st.session_state.votes[voter_name]
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
                    display_voting_results(rounds, st.session_state.books)
                else:
                    st.error("Unable to calculate results")

                if st.button("Hide Results"):
                    st.session_state.show_results = False
                    st.rerun()

if __name__ == '__main__':
    main()

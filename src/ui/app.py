"""
Main Streamlit application.
"""

import streamlit as st
import sys
import os
from pathlib import Path
import logging
import time

src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from core.word_list import WordList
from core.game_engine import WordleGame
from solvers.solver_factory import SolverFactory
from utils.config_loader import ConfigLoader
from utils.metrics import PerformanceMetrics
from ui.components.game_board import render_game_board, render_keyboard
from ui.components.solver_selector import render_solver_selector, render_solver_settings
from ui.components.stats_panel import render_statistics, render_solver_info
from ui.components.word_selection import render_word_selection, render_selection_progress
from ui.components.dashboard import render_dashboard
import time

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Page configuration
st.set_page_config(
    page_title="AI Wordle Solver",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main-header {
        font-size: 48px;
        font-weight: bold;
        text-align: center;
        color: #6aaa64;
        margin-bottom: 10px;
    }
    .sub-header {
        text-align: center;
        color: #787c7e;
        margin-bottom: 30px;
    }
    .stButton>button {
        width: 100%;
        background-color: #6aaa64;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #5a9a54;
    }
</style>
""",
    unsafe_allow_html=True,
)


def initialize_session_state():
    """Initialize Streamlit session state."""
    if "initialized" not in st.session_state:
        config = ConfigLoader()

        # Get the base path for data files
        base_path = Path(__file__).parent.parent.parent
        valid_words_path = base_path / "data" / "words" / "valid_words.txt"
        common_words_path = base_path / "data" / "words" / "common_words.txt"

        # Initialize word list
        word_list = WordList(
            valid_words_path=str(valid_words_path),
            common_words_path=str(common_words_path),
        )

        game = WordleGame(word_list, max_attempts=6)

        metrics = PerformanceMetrics()

        st.session_state.config = config
        st.session_state.word_list = word_list
        st.session_state.game = game
        st.session_state.metrics = metrics
        st.session_state.solver = None
        st.session_state.game_state = None
        st.session_state.auto_play = False
        # Store history of all guesses with their results
        st.session_state.guess_history = []
        st.session_state.initialized = True


def start_new_game(solver_type: str, solver_config: dict, target_word: str = None):
    """Start a new game."""
    solver = SolverFactory.create(
        solver_type, st.session_state.word_list, solver_config
    )
    solver.reset()

    game_state = st.session_state.game.start_new_game(target_word)

    st.session_state.solver = solver
    st.session_state.game_state = game_state
    st.session_state.start_time = time.time()
    st.session_state.guess_history = []  # Reset history for new game


def _fallback_guess():
    """Return a safe fallback guess (prefer common words, else any valid)."""
    wl = st.session_state.word_list
    commons = list(wl.get_common_words() or [])
    valids = list(wl.get_valid_words() or [])
    if commons:
        return commons[0]
    if valids:
        return valids[0]
    # last resort
    return "raise"


def make_solver_guess():
    """Make a guess using the current solver and store results."""
    if st.session_state.solver is None or st.session_state.game_state is None:
        return

    if st.session_state.game_state.is_over:
        return

    try:
        guess = st.session_state.solver.get_next_guess()
    except Exception as ex:
        logger.exception("Solver.get_next_guess() raised an exception:")
        st.error("AI solver failed to produce a guess; using fallback.")
        guess = _fallback_guess()

    if guess is None or not isinstance(guess, str) or len(guess) == 0:
        logger.warning("Solver returned invalid guess: %r. Using fallback.", guess)
        guess = _fallback_guess()

    # Ensure guess is a valid 5-letter word known to the word list if possible
    if hasattr(st.session_state.word_list, "is_valid_word"):
        try:
            if not st.session_state.word_list.is_valid_word(guess):
                logger.warning(
                    "Guess '%s' not in valid word list; using fallback.", guess
                )
                guess = _fallback_guess()
        except Exception:
            # If method fails for some reason, don't block execution
            logger.exception(
                "Error while validating guess with word_list.is_valid_word"
            )

    try:
        success, feedback, error = st.session_state.game.make_guess(guess)
    except Exception:
        logger.exception("game.make_guess raised an exception with guess %r", guess)
        st.error("Game engine failed to accept the guess.")
        return

    if error:
        # If the game returned an error (e.g., invalid word), show it and try a fallback once
        st.warning(f"Game rejected guess '{guess}': {error}")
        fallback = _fallback_guess()
        if fallback != guess:
            try:
                success, feedback, error = st.session_state.game.make_guess(fallback)
            except Exception:
                logger.exception(
                    "game.make_guess raised an exception with fallback %r", fallback
                )
                return
            if not error:
                guess = fallback
            else:
                logger.error("Fallback guess also rejected: %r", error)
                return
        else:
            return

    if success:
        # Get solver stats BEFORE updating state
        solver_stats = st.session_state.solver.get_statistics()

        # Safely update solver state
        try:
            st.session_state.solver.update_state(guess, feedback)
        except Exception:
            logger.exception(
                "solver.update_state raised an exception for guess %r", guess
            )
            # continue — we still want to update UI even if solver had an error

        # Store the result for UI display
        guess_result = {
            "attempt": st.session_state.game_state.attempts,
            "guess": guess,
            "feedback": feedback,
            "remaining_words": len(st.session_state.solver.possible_words),
            "candidates": solver_stats.get("candidates", []),
            "selection_info": solver_stats.get("selection_info", {}),
        }
        st.session_state.guess_history.append(guess_result)

        # Check if game is over

        if st.session_state.game_state.is_over:
            elapsed_time = time.time() - st.session_state.start_time
            st.session_state.metrics.add_game(
                st.session_state.game_state.is_won,
                st.session_state.game_state.attempts,
                elapsed_time,
            )



def main():
    """Main application."""
    initialize_session_state()

    st.markdown(
        '<div class="main-header">🎮 AI Wordle Solver</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="sub-header">Multiple AI Algorithms Competing to Solve Wordle</div>',
        unsafe_allow_html=True,
    )

    solver_type = render_solver_selector()
    solver_config = render_solver_settings(solver_type)

    render_statistics(st.session_state.metrics.get_summary())

    # Non-interactive comparison dashboard (dynamic)
    try:
        available = SolverFactory.get_available_solvers()
        other_solver = next((s for s in available if s != solver_type), available[0] if available else solver_type)
        render_dashboard(solver_type, other_solver, st.session_state.word_list)
    except Exception:
        logger.exception("render_dashboard failed")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button("🎲 New Game"):
                start_new_game(solver_type, solver_config)
                st.rerun()

        with col_b:
            if st.button("🤖 AI Guess"):
                make_solver_guess()
                st.rerun()

        with col_c:
            auto_play = st.checkbox("⚡ Auto Play", value=st.session_state.auto_play)
            st.session_state.auto_play = auto_play

        with st.expander("🎯 Custom Target Word"):
            custom_word = st.text_input(
                "Enter a 5-letter word (optional)", max_chars=5
            ).lower()
            if st.button("Start with Custom Word") and len(custom_word) == 5:
                start_new_game(solver_type, solver_config, custom_word)
                st.rerun()

        st.divider()

        if st.session_state.game_state:
            render_game_board(
                st.session_state.game_state.guesses,
                st.session_state.game_state.feedbacks,
                st.session_state.game.max_attempts,
            )

            if st.session_state.game_state.is_over:
                if st.session_state.game_state.is_won:
                    st.success(
                        f"🎉 Solved in {st.session_state.game_state.attempts} guesses!"
                    )
                else:
                    st.error(
                        f"😞 Failed! The word was: "
                        f"**{st.session_state.game_state.target_word.upper()}**"
                    )
            else:
                st.info(
                    f"Attempt {st.session_state.game_state.attempts + 1} "
                    f"of {st.session_state.game.max_attempts}"
                )

            render_keyboard(
                st.session_state.game_state.guesses,
                st.session_state.game_state.feedbacks,
            )

            # Divider before history
            st.divider()

            # Display all guess results history
            if st.session_state.guess_history:
                st.subheader("📋 Guess History")
                
                for result in st.session_state.guess_history:
                    with st.expander(
                        f"Attempt {result['attempt']}: {result['guess'].upper()} "
                        f"({result['remaining_words']} words remaining)",
                        expanded=(result['attempt'] == len(st.session_state.guess_history))
                    ):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Guessed Word:** {result['guess'].upper()}")
                            st.write(f"**Remaining Candidates:** {result['remaining_words']}")

                        with col2:
                            selection_info = result.get("selection_info", {})
                            if selection_info:
                                st.write(f"**Algorithm:** {selection_info.get('method', 'N/A')}")
                                if "entropy" in selection_info:
                                    st.write(f"**Entropy:** {selection_info.get('entropy', 'N/A')}")

                        # Show top candidates
                        candidates = result.get("candidates", [])
                        if candidates:
                            st.write("**Top Candidates Considered:**")
                            for i, cand in enumerate(candidates, 1):
                                st.write(
                                    f"{i}. {cand.get('word', '').upper()} "
                                    f"(Score: {cand.get('score', 'N/A')})"
                                )

                st.divider()

            # Current solver info
            if st.session_state.solver:
                try:
                    solver_stats = st.session_state.solver.get_statistics()

                    # Show selection progress
                    render_selection_progress(
                        st.session_state.game_state.guesses,
                        solver_stats.get("remaining_words", 0),
                        len(st.session_state.word_list.get_common_words()),
                    )

                    st.divider()

                    # Show general solver info
                    render_solver_info(solver_stats)

                except Exception:
                    logger.exception("render_solver_info failed")


        else:
            st.info("👆 Click 'New Game' to start!")


    # Auto-play logic - store without rerun for speed
    if (
        st.session_state.auto_play
        and st.session_state.game_state
        and not st.session_state.game_state.is_over
    ):
        time.sleep(0.5)
        make_solver_guess()
        st.rerun()


if __name__ == "__main__":
    main()

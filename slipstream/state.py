# Importing libraries
import reflex as rx


# Creating the app state to keep track of the question, answer and chat history
class State(rx.State):

    # The current question being asked
    question: str = ""

    # Keep track of the chat history as a list of (question, answer) tuples
    chat_history: list[tuple[str, str]] = list()

    # Define the event handlers to manipulate both the current question and the chat history
    @rx.event
    def set_question(self, value: str):
        self.question = value

    @rx.event
    def answer(self):

        # Not very smart right now...
        answer: str = "I don't know!"
        self.chat_history.append((self.question, answer))

        # Clear the question value to empty the binded input in the UI
        self.question = ""

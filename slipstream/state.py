# Importing libraries
import reflex as rx
import asyncio


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
    async def answer(self):

        # Not very smart right now...
        answer: str = "I don't know!"
        self.chat_history.append((self.question, answer))

        # Clear the question value to empty the binded input in the UI
        self.question = ""
        yield

        # Streaming one letter at a time to simulate the response being builted live by a chatbot
        for i in range(len(answer)):
            await asyncio.sleep(0.1)
            self.chat_history[-1] = (self.chat_history[-1][0], answer[: i + 1])
            yield

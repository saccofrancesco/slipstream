# Importing libraries
import reflex as rx

# App's styles and state imports
from slipstream import style
from slipstream.state import State


# Q&A component to display question and answers as like in a chat
def qa(question: str, answer: str) -> rx.Component:
    return rx.box(
        rx.box(rx.text(question, style=style.question_style), text_align="right"),
        rx.box(rx.text(answer, style=style.answer_style), text_align="left"),
        margin_y="1em",
        width="100%",
    )


# Chat component containing multiple Q&A components instances
def chat() -> rx.Component:
    return rx.box(
        rx.foreach(State.chat_history, lambda messages: qa(messages[0], messages[1]))
    )


# Component for the user interaction section
def action_bar() -> rx.Component:
    return rx.hstack(
        rx.input(
            value=State.question,
            placeholder="Ask a question",
            style=style.input_style,
            on_change=State.set_question,
        ),
        rx.button("Ask", style=style.button_style, on_click=State.answer),
        width="100%",
    )


# Main application page component
def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            chat(),
            action_bar(),
            align="stretch",
            width="100%",
            max_width="48em",
            padding="1em",
        )
    )


# Instanciating the app object and adding the index page as the root
app: rx.App = rx.App()
app.add_page(index)

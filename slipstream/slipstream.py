# Importing libraries
import reflex as rx

# App's styles imports
from slipstream import style


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
    qa_pairs: list[tuple[str, str]] = [
        ("What is Reflex?", "A way to build web apps in pure Python!"),
        (
            "What can I make with it?",
            "Anything from a simple website to a complex web app!",
        ),
    ]
    return rx.box(*[qa(question, answer) for question, answer in qa_pairs])


# Component for the user interaction section
def action_bar() -> rx.Component:
    return rx.hstack(
        rx.input(placeholder="Ask a question", style=style.input_style),
        rx.button("Ask", style=style.button_style),
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

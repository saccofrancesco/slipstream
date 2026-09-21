# Importing libraries
import reflex as rx


# Q&A component to display question and answers as like in a chat
def qa(question: str, answer: str) -> rx.Component:
    return rx.box(
        rx.box(question, text_align="right"),
        rx.box(answer, text_align="left"),
        margin_y="1em",
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
    return rx.hstack(rx.input(placeholder="Ask a question"), rx.button("Ask"))


# Main application page component
def index() -> rx.Component:
    return rx.container(chat(), action_bar())


# Instanciating the app object and adding the index page as the root
app: rx.App = rx.App()
app.add_page(index)

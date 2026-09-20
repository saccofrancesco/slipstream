# Importing libraries
import dataclasses
from collections import Counter
import reflex as rx


# Defining the model to describe user's data accessible via dot notation
@dataclasses.dataclass
class User:
    """The user model"""

    name: str
    email: str
    gender: str  # Male or Female


# Defining the state variblaes of the application and the methods to manipulate them
class State(rx.State):

    # Creating the default list, with already some user inside
    users: list[User] = [
        User(name="Danilo Sousa", email="danilo@example.com", gender="Male"),
        User(name="Zahra Ambessa", email="zahra@example.com", gender="Female"),
    ]

    # Defining a variable that keeps track of users in a converted way, suitable to pass to graph functions
    users_for_graph: list[dict[str, str]] = list()

    # Keeps track if the dialog is opened or not
    add_user_dialog_open: bool = False

    # Dialog open state varibale toggle
    @rx.event
    def set_add_user_dialog_open(self, open_: bool):
        """Set whether the add-user dialog is open"""
        self.add_user_dialog_open = open_

    # Add a user dataclass to the list of users
    @rx.event
    def add_user(self, form_data: dict):
        self.users.append(User(**form_data))

        # Transofrm method to also update the suitable version for graphs
        self.transform_data()

        # Manually setting the dialog open to false on action closing
        self.add_user_dialog_open = False

    # Helper method (no event handler) to manipulate and transofrm list of dataclass in suitable dict for charting
    def transform_data(self):
        """Transform user gender group data into a format suitable for visualization in graphs"""
        # Count users of each gender group
        gender_counts = Counter(user.gender for user in self.users)

        # Transform into list of dict so it can be used in the graph
        self.users_for_graph = [
            {"name": gender_group, "value": count}
            for gender_group, count in gender_counts.items()
        ]


# Component that show a table row with the unpacked user's informations inside its cells
def show_user(user: User):
    """Show a user in a table row"""
    return rx.table.row(
        rx.table.cell(user.name),
        rx.table.cell(user.email),
        rx.table.cell(user.gender),
        style={"_hover": {"bg": rx.color("gray", 3)}},
        align="center",
    )


# CTA button component to show the dialog and submit the form to add a new customer to the pool
def add_customer_button() -> rx.Component:
    return rx.dialog.root(
        # The trigger which will be visible and interactable to open the content of the dialog
        rx.dialog.trigger(
            rx.button(
                rx.icon("plus", size=18),
                rx.text("Add User", size="2"),
            ),
        ),
        # The actual content of the opene dialog
        rx.dialog.content(
            # Setting the title and the description
            rx.dialog.title(
                "Add New User",
            ),
            rx.dialog.description(
                "Fill the form with the user's info",
            ),
            # Nesting the form component inside the modal
            rx.form(
                # Placing using flex the inputs
                rx.flex(
                    rx.input(placeholder="User Name", name="name", required=True),
                    rx.input(
                        placeholder="user@reflex.dev",
                        name="email",
                    ),
                    rx.select(
                        ["Male", "Female"],
                        placeholder="Select gender",
                        default_value="Male",
                        name="gender",
                        custom_attrs={"aria-label": "Gender"},
                    ),
                    # Placing inline the 2 action buttons
                    rx.flex(
                        # Inside the close slot of the dialog component put the cancel to undo the operation
                        rx.dialog.close(
                            rx.button(
                                "Cancel",
                                type="button",
                                variant="soft",
                                color_scheme="gray",
                            ),
                        ),
                        # Placing instead the sumbit button outside and add the type to make the pop-up automatically close
                        rx.button("Submit", type="submit"),
                        spacing="3",
                        justify="end",
                    ),
                    direction="column",
                    spacing="4",
                ),
                # Specifying the behaviour of the form
                on_submit=State.add_user,
                reset_on_submit=False,
            ),
            max_width="450px",
        ),
        # Linking the opening of the modal to the state varibale toggler
        open=State.add_user_dialog_open,
        on_open_change=State.set_add_user_dialog_open,
    )


# Chart component to dispaly the number of male and female customers among the list in a horizontal barchart
def graph() -> rx.Component:
    return rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(
            horizontal=False, stroke_dasharray="3 3", stroke=rx.color("slate", 4)
        ),
        # Specify the appearance of both axis and of the bars
        rx.recharts.x_axis(
            type_="number",
            allow_decimals=False,
            axis_line=False,
            tick_line=False,
            domain=[0, "dataMax + 1"],
        ),
        rx.recharts.y_axis(
            type_="category",
            data_key="name",
            axis_line=False,
            tick_line=False,
            width=64,
        ),
        rx.recharts.bar(
            data_key="value",
            fill=rx.color("accent", 9),
            radius=[0, 6, 6, 0],
            bar_size=28,
        ),
        # Which data to gather the infos from
        data=State.users_for_graph,
        layout="vertical",
        width="100%",
        height=160,
        margin={"top": 0, "right": 16, "bottom": 0, "left": 0},
    )


# Root page component where each individual section is placed on positioned in a layout
def index() -> rx.Component:
    return rx.box(
        rx.box(
            rx.box(
                rx.box(
                    rx.heading("Customers", size="6", as_="h3", margin="0"),
                    rx.badge(
                        State.users.length(),
                        variant="soft",
                        color_scheme="gray",
                        radius="full",
                    ),
                    display="flex",
                    align_items="center",
                    gap="12px",
                ),
                rx.text(
                    "Your customer directory and audience breakdown.",
                    size="2",
                    color=rx.color("slate", 11),
                    margin_top="6px",
                ),
            ),
            add_customer_button(),
            display="flex",
            align_items="center",
            justify_content="space-between",
            flex_wrap="wrap",
            gap="16px",
            padding="24px",
        ),
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Name"),
                        rx.table.column_header_cell("Email"),
                        rx.table.column_header_cell("Gender"),
                    )
                ),
                rx.table.body(rx.foreach(State.users, show_user)),
                variant="ghost",
                size="3",
                width="100%",
            ),
            overflow_x="auto",
            width="100%",
            border_top=f"1px solid {rx.color('slate', 4)}",
            border_bottom=f"1px solid {rx.color('slate', 4)}",
            padding_x="12px",
        ),
        rx.box(
            rx.text("Audience breakdown", size="3", weight="bold"),
            rx.text(
                "Customers by gender",
                size="2",
                color=rx.color("slate", 11),
                margin_top="4px",
                margin_bottom="20px",
            ),
            graph(),
            padding="24px",
        ),
        width="100%",
        min_width="0",
        max_width="64em",
        margin_x="auto",
        margin_y="24px",
        border=f"1px solid {rx.color('slate', 5)}",
        border_radius="16px",
        background=rx.color("slate", 1),
        overflow="hidden",
        box_shadow="0 4px 24px rgba(0, 0, 0, 0.03)",
        style={
            "& *": {"box_sizing": "border-box"},
            "& p, & h3": {"text_align": "left"},
        },
    )


# Instanciating the app object and adding the index page as the root
app = rx.App()
app.add_page(
    index,
    title="Customer Data App",
    description="A simple app to manage customer data",
    on_load=State.transform_data,
)

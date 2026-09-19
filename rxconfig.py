import reflex as rx

config = rx.Config(
    app_name="slipstream",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(radius="full", accent_color="grass"),
        ),
    ],
)

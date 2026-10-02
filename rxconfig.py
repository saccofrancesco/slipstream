"""Configure the Reflex plugins used by the Slipstream application."""

# Reflex provides the configuration and plugin interfaces used below.
import reflex as rx

# Enable the plugins that provide site maps, Tailwind styles, and Radix themes.
config: rx.Config = rx.Config(
    app_name="slipstream",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(accent_color="red"),
        ),
    ],
)

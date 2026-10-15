<div align="center">
  <img src="assets/icons/icon.svg" alt="Slipstream logo" width="180">
  <h1>Slipstream: Explore Formula 1 Results</h1>
</div>

<p align="center">
  <a href="https://buymeacoffee.com/saccofrancesco">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me a Coffee">
  </a>
</p>

<h4 align="center">A Formula 1 results dashboard for race weekends, championship standings, session classifications, and lap times — built with <a href="https://reflex.dev">Reflex</a> and powered by <a href="https://docs.fastf1.dev">FastF1</a>.</h4>

<p align="center"><a href="https://slipstream-lime-star.reflex.run"><strong>🌐 Try Slipstream live</strong></a></p>

<p align="center">
  <img src="https://img.shields.io/github/contributors/saccofrancesco/slipstream?style=for-the-badge" alt="Contributors">
  <img src="https://img.shields.io/github/forks/saccofrancesco/slipstream?style=for-the-badge" alt="Forks">
  <img src="https://img.shields.io/github/stars/saccofrancesco/slipstream?style=for-the-badge" alt="Stars">
</p>

<p align="center">
  <a href="#tldr">TL;DR</a> •
  <a href="#key-features">Key Features</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#credits--acknowledgements">Credits</a> •
  <a href="#license">License</a>
</p>

---

## 📌 TL;DR

Slipstream brings Formula 1 race data into one place. Follow the current or next race weekend, revisit completed Grands Prix, compare session lap times, and check the latest driver and team championship standings.

---

## 💡 Why Slipstream Stands Out

- **Race weekend at a glance:** See the session schedule in your timezone or the circuit's local time.
- **Results across the weekend:** Open classifications for published practice, qualifying, Sprint, and race sessions.
- **Lap comparisons:** Select drivers to compare lap times, spot tyre compounds, and choose whether to show flagged outliers.
- **Season context:** Browse completed races and the latest driver and constructor standings.

---

## 🔑 Key Features

* **Results hub** – Shows the current or upcoming Grand Prix, its schedule, and an archive of completed races from the season.
* **Session classifications** – Displays available session results, including practice, qualifying, Sprint, and race classifications where data exists.
* **Interactive lap chart** – Plots selected drivers' timed laps with tyre compound markers and an outlier toggle. Laps load when you open the Laps tab.
* **Championship standings** – Presents the latest driver and team standings after a completed race.
* **Responsive interface** – Uses Reflex components across the results and championship pages.

The event page includes an interactive **Telemetry** tab for comparing selected laps.

---

## ⚡ Quickstart

Use the [hosted app](https://slipstream-lime-star.reflex.run) right away, or run it locally with Python **3.14**. A local run needs an internet connection to load Formula 1 data.

```bash
git clone https://github.com/saccofrancesco/slipstream.git
cd slipstream
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
reflex run
```

Open **http://localhost:3000** once Reflex starts. On Windows, activate the virtual environment with `.venv\Scripts\activate` before installing dependencies.

---

## 📬 Emailware: Share Your Thoughts

Slipstream is [emailware](https://en.wiktionary.org/wiki/emailware). If you find it useful or have an idea for it, I’d love to hear from you!

Send feedback to: **[francescosacco.github@gmail.com](mailto:francescosacco.github@gmail.com)**

---

## 🙏 Love Slipstream? Support It!

If this project helped you or you just think it’s cool:

* ⭐️ [Star the repo](https://github.com/saccofrancesco/slipstream)
* 🧃 [Buy me a coffee](https://www.buymeacoffee.com/saccofrancesco)
* 💌 Send your thoughts or suggestions by email

---

## 🧠 Credits & Acknowledgements

Slipstream uses the following libraries and data sources:

* [Python](https://www.python.org/)
* [Reflex](https://reflex.dev/)
* [FastF1](https://docs.fastf1.dev/)
* [Ergast API via FastF1](https://docs.fastf1.dev/ergast.html) for calendars and standings
* [Formula 1 timing data via FastF1](https://docs.fastf1.dev/core.html) for session results and laps

---

## 📎 You Might Also Like...

Check out another project by the same author:

* [DeepShot](https://github.com/saccofrancesco/supremebot): An NBA game prediction model software built with [XGBoost](https://xgboost.readthedocs.io/en/release_3.0.0/) and [NiceGUI](https://nicegui.io/).
* [Supremebot](https://github.com/saccofrancesco/supremebot): A Supreme shopping assistant built with [NiceGUI](https://nicegui.io/).

---

## 📜 License

See the [LICENSE](LICENSE) file for license terms.

---

> GitHub [@saccofrancesco](https://github.com/saccofrancesco)

import marimo

__generated_with = "0.23.14"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Hebog source-finder demonstration

    This Marimo notebook will become a small, reproducible source-finding
    example as the scientific implementation is developed.
    """)
    return


if __name__ == "__main__":
    app.run()

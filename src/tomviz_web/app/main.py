from .core import Tomviz


def main(server=None, **kwargs):
    app = Tomviz(server)
    app.server.start(**kwargs)


if __name__ == "__main__":
    main()

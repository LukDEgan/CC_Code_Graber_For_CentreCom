import tkinter as tk

from gui import TicketApp


def main():
    root = tk.Tk()

    app = TicketApp(root)

    root.mainloop()


if __name__ == "__main__":
    main()

import tkinter as tk
from tkinter import ttk
import tkinter.messagebox
import os
import json

class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GUI")
        self.geometry("400x400")
        self.resizable(0,0)
        self.create_widgets()
        self.settings = self.load_config()

    def create_widgets(self):
        self.label = ttk.Label(self, text="Hello World!")
        self.label.grid(row=0, column=0, padx=5, pady=5)

        self.button = ttk.Button(self, text="Click Me!", command=self.click_me)
        self.button.grid(row=1, column=0, padx=5, pady=5)

    def click_me(self):
        self.label.configure(text="I was clicked!")

    def load_config(self):
        try:
            with open('settings.json', 'r') as f:
                return json.loads(f.read())
        except FileNotFoundError:
            tk.messagebox.showinfo('Settings file not found', 'Settings file not found, creating new one')   
            settings = {'authorization_token': '', 'refresh_token': '', 'playlists': [], 'merge_playlist': ''}
            with open('settings.json', 'w') as f:
                f.write(json.dumps(settings, indent=2))
            return settings
        except json.JSONDecodeError:
            if tk.messagebox.askyesno('Settings file corrupted', 'Settings file corrupted, would you like to create a new one?'):
                settings = {'authorization_token': '', 'refresh_token': '', 'playlists': [], 'merge_playlist': ''}
                with open('settings.json', 'w') as f:
                    f.write(json.dumps(settings, indent=2))
                return settings
            else:
                tk.messagebox.showinfo('Settings file corrupted', 'Settings file corrupted, please delete settings.json and restart the program')
            self.destroy()
            f.write(json.dumps(settings, indent=2))

if __name__ == "__main__":
    gui = GUI()
    gui.mainloop()
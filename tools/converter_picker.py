"""A short-lived native chooser, isolated from HTTP worker threads."""
import sys
import tkinter as tk
from tkinter import filedialog

if __name__=='__main__':
    app=tk.Tk();app.withdraw();app.attributes('-topmost',True)
    kind=sys.argv[1] if len(sys.argv)>1 else 'file'
    value=filedialog.askdirectory(title='选择目录') if kind=='directory' else filedialog.askopenfilename(title='选择存档或配置文件')
    sys.stdout.reconfigure(encoding='utf-8');print(value);app.destroy()

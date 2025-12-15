import customtkinter as ctk
import os
import json
import threading
import ollama
from datetime import datetime
import tkinter.messagebox as msgbox
from tkinter import filedialog

COLOR_BG = ("#F8F9FA", "#0F0F0F")
COLOR_SIDEBAR = ("#FFFFFF", "#181818")
COLOR_CARD = ("#FFFFFF", "#242424")
COLOR_TEXT = ("#1F2937", "#FFFFFF")
COLOR_TEXT_SUB = ("#6B7280", "#9CA3AF")
COLOR_ACCENT = ("#3B82F6", "#3B82F6")
COLOR_BORDER = ("#E5E7EB", "#2E2E2E")

FONT_HEADER = ("Segoe UI", 24, "bold")
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_BODY = ("Segoe UI", 14)

MODEL_OPTIONS = {
    "Smart (Gemma 3n 4B)": "gemma3n:e4b",
    "Balanced (Gemma 3n 2B)": "gemma3n:e2b",
    "Fast (Gemma 3 1B)": "gemma3:1b"
}

DEFAULT_PERSONA = "You are an AI tutor using the Feynman Technique. I will explain a concept in my own words. Your job is to: Carefully analyze my explanation, Ask me clear, progressively harder questions based ONLY on what I explained, Ask follow-up questions that force me to clarify or simplify, Avoid teaching or correcting unless I explicitly ask Rules: Ask one question at a time Start simple, then increase difficulty If my explanation is weak, ask “why”, “how”, or “what happens if” If something is missing, ask directly about it Do NOT add new information that I didn’t mention After each answer I give, continue questioning until the concept is fully clear and rigorous. Acknowledge when the explanation is complete and solid. If I am wrong, say that I am, and remember this."

class StudyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Feynman AI")
        self.geometry("1200x800")
        ctk.set_appearance_mode("System") 
        ctk.set_default_color_theme("blue")
        
        self.flagged_questions = self.load_json("review.json")
        self.settings = self.load_settings()
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_main_area()
        
        self.show_frame("TutorFrame")

    def load_json(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, "r") as f: return json.load(f)
            except: return []
        return []

    def load_settings(self):
        defaults = {
            "model": "gemma3n:e2b",
            "system_prompt": DEFAULT_PERSONA,
            "temperature": 0.7,
            "theme": "System"
        }
        if os.path.exists("settings.json"):
            try:
                with open("settings.json", "r") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except: pass
        return defaults

    def save_json(self, filename, data):
        with open(filename, "w") as f: json.dump(data, f, indent=4)

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=COLOR_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        logo = ctk.CTkLabel(self.sidebar, text="Feynman AI", font=("Segoe UI", 26, "bold"), text_color=COLOR_ACCENT)
        logo.grid(row=0, column=0, padx=25, pady=(35, 30), sticky="w")
        
        self.nav_buttons = {}
        items = [
            ("🎓  Tutor", "TutorFrame"),
            ("🚩  Review", "ReviewFrame"),
            ("⚙️  Settings", "SettingsFrame")
        ]

        for i, (text, frame_name) in enumerate(items):
            btn = ctk.CTkButton(
                self.sidebar, 
                text=text, 
                command=lambda n=frame_name: self.show_frame(n),
                fg_color="transparent", 
                text_color=COLOR_TEXT_SUB, 
                hover_color=("gray90", "gray25"),
                anchor="w",
                font=("Segoe UI", 15, "bold"),
                height=45,
                corner_radius=8
            )
            btn.grid(row=i+1, column=0, padx=15, pady=5, sticky="ew")
            self.nav_buttons[frame_name] = btn

    def setup_main_area(self):
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOR_BG)
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (TutorFrame, ReviewFrame, SettingsFrame):
            page_name = F.__name__
            frame = F(parent=self.main_container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

    def show_frame(self, name):
        for key, btn in self.nav_buttons.items():
            if key == name:
                btn.configure(fg_color=COLOR_ACCENT, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=COLOR_TEXT_SUB)
        
        frame = self.frames[name]
        frame.tkraise()
        if hasattr(frame, "on_show"): frame.on_show()

class TutorFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.messages = []
        self.last_ai_msg = ""
        self.last_user_msg = ""

        self.chat_display = ctk.CTkTextbox(self, font=("Segoe UI", 16), wrap="word", 
                                         fg_color=COLOR_CARD, text_color=COLOR_TEXT, corner_radius=0)
        self.chat_display.pack(fill="both", expand=True, padx=0, pady=0)
        self.chat_display.configure(state="disabled")

        # --- TOOLBAR ---
        self.action_bar = ctk.CTkFrame(self, fg_color="transparent", height=50)
        self.action_bar.pack(fill="x", padx=20, pady=10)
        
        # Left Side (Session Management)
        self.btn_refresh = ctk.CTkButton(self.action_bar, text="New Session", width=100, fg_color="#10B981", hover_color="#059669", command=self.start_new_session)
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_save = ctk.CTkButton(self.action_bar, text="💾 Save Chat", width=100, fg_color="#6366F1", hover_color="#4F46E5", command=self.save_chat_history)
        self.btn_save.pack(side="left", padx=5)

        # Right Side (Response Actions)
        self.btn_flag = ctk.CTkButton(self.action_bar, text="🚩 Flag Question", fg_color="#EF4444", 
                                      hover_color="#B91C1C", command=self.flag_question)
        self.btn_flag.pack(side="right", padx=5)

        self.btn_retry = ctk.CTkButton(self.action_bar, text="🔄 Retry Last", width=100, fg_color="gray50", command=self.retry_last)
        self.btn_retry.pack(side="right", padx=5)
        
        # --- INPUT ---
        self.input_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, height=80, corner_radius=0)
        self.input_frame.pack(fill="x", side="bottom")
        
        self.entry = ctk.CTkEntry(self.input_frame, placeholder_text="Ask Feynman AI...", height=50, font=FONT_BODY, border_width=0, fg_color="transparent")
        self.entry.pack(side="left", fill="x", expand=True, padx=20)
        self.entry.bind("<Return>", self.send_message)
        
        btn_send = ctk.CTkButton(self.input_frame, text="➤", width=50, height=40, fg_color=COLOR_ACCENT, command=self.send_message)
        btn_send.pack(side="right", padx=20)

    def on_show(self):
        if not self.messages:
            self.start_new_session(confirm=False)

    def start_new_session(self, confirm=True):
        if confirm:
            if not msgbox.askyesno("New Session", "Are you sure you want to clear the chat history?"):
                return
        
        system_p = self.controller.settings.get("system_prompt", DEFAULT_PERSONA)
        self.messages = [{"role": "system", "content": system_p}]
        
        self.chat_display.configure(state="normal")
        self.chat_display.delete("0.0", "end")
        self.chat_display.configure(state="disabled")
        
        self.last_ai_msg = ""
        self.last_user_msg = ""

    def save_chat_history(self):
        if len(self.messages) <= 1:
            msgbox.showinfo("Info", "No chat history to save.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        default_name = f"feynman_chat_{timestamp}.txt"
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=default_name
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"Feynman AI Chat Log - {timestamp}\n")
                    f.write("="*40 + "\n\n")
                    for msg in self.messages:
                        if msg['role'] == 'system': continue
                        role = "User" if msg['role'] == 'user' else "Feynman"
                        f.write(f"[{role}]:\n{msg['content']}\n\n{'-'*20}\n\n")
                msgbox.showinfo("Saved", "Chat history saved successfully.")
            except Exception as e:
                msgbox.showerror("Error", f"Failed to save file: {e}")

    def send_message(self, event=None):
        msg = self.entry.get()
        if not msg: return
        self.entry.delete(0, "end")
        
        self.append_chat("You", msg)
        self.last_user_msg = msg
        self.messages.append({"role": "user", "content": msg})
        
        threading.Thread(target=self.run_ai).start()

    def run_ai(self):
        try:
            full_response = ""
            options = {
                "temperature": self.controller.settings.get("temperature", 0.7)
            }
            
            stream = ollama.chat(model=self.controller.settings["model"], messages=self.messages, stream=True, options=options)
            
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", "\nFeynman: ", "ai_tag")
            
            for chunk in stream:
                text = chunk['message']['content']
                full_response += text
                self.chat_display.insert("end", text)
                self.chat_display.see("end")
                
            self.chat_display.insert("end", "\n")
            self.chat_display.configure(state="disabled")
            
            self.last_ai_msg = full_response
            self.messages.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            self.append_chat("System", f"Error: {str(e)}")

    def append_chat(self, role, text):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"\n{role}: {text}\n")
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def retry_last(self):
        if not self.last_user_msg: return
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages.pop()
        self.append_chat("System", "--- Retrying ---")
        threading.Thread(target=self.run_ai).start()

    def flag_question(self):
        if not self.last_ai_msg:
            msgbox.showwarning("Flag", "No AI message to flag yet.")
            return
            
        item = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "question": self.last_ai_msg,
            "context": self.last_user_msg
        }
        
        self.controller.flagged_questions.append(item)
        self.controller.save_json("review.json", self.controller.flagged_questions)
        msgbox.showinfo("Flagged", "Question saved to Review Sidebar.")

class ReviewFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        ctk.CTkLabel(self, text="Flagged For Review", font=FONT_HEADER, text_color=COLOR_TEXT).pack(pady=20, padx=40, anchor="w")
        
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

    def on_show(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        items = self.controller.flagged_questions
        
        if not items:
            ctk.CTkLabel(self.scroll, text="No flagged questions yet.", font=FONT_TITLE, text_color="gray").pack(pady=50)
            return

        for i, item in enumerate(items):
            self.create_review_card(i, item)

    def create_review_card(self, index, item):
        card = ctk.CTkFrame(self.scroll, fg_color=COLOR_CARD, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=5, padx=10)
        
        top = ctk.CTkFrame(card, fg_color="transparent", height=30)
        top.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(top, text=item["date"], font=("Segoe UI", 12), text_color=COLOR_TEXT_SUB).pack(side="left")
        ctk.CTkButton(top, text="🗑", width=30, fg_color="transparent", text_color="red", 
                      command=lambda idx=index: self.delete_item(idx)).pack(side="right")

        ctk.CTkLabel(card, text=f"Trigger: {item['context']}", font=("Segoe UI", 12, "italic"), text_color=COLOR_TEXT_SUB, anchor="w").pack(fill="x", padx=15)
        
        ctk.CTkLabel(card, text=item["question"], font=("Segoe UI", 14), text_color=COLOR_TEXT, justify="left", wraplength=600).pack(fill="x", padx=15, pady=(5, 15))

    def delete_item(self, index):
        del self.controller.flagged_questions[index]
        self.controller.save_json("review.json", self.controller.flagged_questions)
        self.on_show()

class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(self.scroll, text="Settings", font=FONT_HEADER, text_color=COLOR_TEXT).pack(pady=30, padx=40, anchor="w")

        self.create_ai_settings()
        self.create_appearance_settings()
        self.create_data_settings()

    def create_ai_settings(self):
        frame = ctk.CTkFrame(self.scroll, fg_color=COLOR_CARD, corner_radius=15)
        frame.pack(fill="x", padx=40, pady=(0, 20))
        
        ctk.CTkLabel(frame, text="Brain Configuration", font=FONT_TITLE, text_color=COLOR_ACCENT).pack(pady=(20, 10), padx=20, anchor="w")

        row1 = ctk.CTkFrame(frame, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(row1, text="Ollama Model:", font=FONT_BODY, text_color=COLOR_TEXT).pack(side="left")
        
        self.model_var = ctk.StringVar(value=self.get_model_name_by_tag(self.controller.settings["model"]))
        self.opt_model = ctk.CTkOptionMenu(row1, values=list(MODEL_OPTIONS.keys()), variable=self.model_var, width=250)
        self.opt_model.pack(side="right")

        row2 = ctk.CTkFrame(frame, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(row2, text="System Persona:", font=FONT_BODY, text_color=COLOR_TEXT).pack(side="left")
        ctk.CTkButton(row2, text="Restore Default", width=100, height=24, fg_color="transparent", 
                      border_width=1, border_color=COLOR_BORDER, text_color=COLOR_TEXT_SUB, 
                      command=self.restore_default_persona).pack(side="right")
        
        self.txt_prompt = ctk.CTkTextbox(frame, height=80, font=("Segoe UI", 12), text_color=COLOR_TEXT)
        self.txt_prompt.insert("0.0", self.controller.settings["system_prompt"])
        self.txt_prompt.pack(fill="x", padx=20, pady=(0, 10))

        row3 = ctk.CTkFrame(frame, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(row3, text="Creativity (Temperature):", font=FONT_BODY, text_color=COLOR_TEXT).pack(side="left")
        self.lbl_temp = ctk.CTkLabel(row3, text=str(self.controller.settings["temperature"]), font=FONT_BODY, text_color=COLOR_TEXT_SUB)
        self.lbl_temp.pack(side="right", padx=10)
        self.slider_temp = ctk.CTkSlider(row3, from_=0.0, to=1.0, command=self.update_temp_label)
        self.slider_temp.set(self.controller.settings["temperature"])
        self.slider_temp.pack(side="right", padx=10)

    def create_appearance_settings(self):
        frame = ctk.CTkFrame(self.scroll, fg_color=COLOR_CARD, corner_radius=15)
        frame.pack(fill="x", padx=40, pady=(0, 20))
        
        ctk.CTkLabel(frame, text="Appearance", font=FONT_TITLE, text_color=COLOR_ACCENT).pack(pady=(20, 10), padx=20, anchor="w")
        
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkLabel(row, text="App Theme:", font=FONT_BODY, text_color=COLOR_TEXT).pack(side="left")
        self.seg_theme = ctk.CTkSegmentedButton(row, values=["Light", "Dark", "System"], command=self.change_theme)
        self.seg_theme.set(self.controller.settings.get("theme", "System"))
        self.seg_theme.pack(side="right")

    def create_data_settings(self):
        frame = ctk.CTkFrame(self.scroll, fg_color=COLOR_CARD, corner_radius=15)
        frame.pack(fill="x", padx=40, pady=(0, 20))
        
        ctk.CTkLabel(frame, text="Data Management", font=FONT_TITLE, text_color="red").pack(pady=(20, 10), padx=20, anchor="w")
        
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(row, text="Clear All Flagged Questions", fg_color="red", command=self.clear_data).pack(side="left")
        
        ctk.CTkButton(self.scroll, text="Save All Settings", height=50, fg_color=COLOR_ACCENT, font=FONT_TITLE, command=self.save_settings).pack(pady=30)

    def get_model_name_by_tag(self, tag):
        for name, t in MODEL_OPTIONS.items():
            if t == tag: return name
        return list(MODEL_OPTIONS.keys())[0]

    def update_temp_label(self, value):
        self.lbl_temp.configure(text=f"{value:.1f}")

    def change_theme(self, value):
        ctk.set_appearance_mode(value)

    def restore_default_persona(self):
        self.txt_prompt.delete("0.0", "end")
        self.txt_prompt.insert("0.0", DEFAULT_PERSONA)

    def save_settings(self):
        selected_model_name = self.opt_model.get()
        self.controller.settings["model"] = MODEL_OPTIONS[selected_model_name]
        self.controller.settings["system_prompt"] = self.txt_prompt.get("0.0", "end").strip()
        self.controller.settings["temperature"] = round(self.slider_temp.get(), 1)
        self.controller.settings["theme"] = self.seg_theme.get()
        
        self.controller.save_json("settings.json", self.controller.settings)
        msgbox.showinfo("Success", "Settings saved successfully.")

    def clear_data(self):
        if msgbox.askyesno("Confirm", "Are you sure you want to delete all flagged questions?"):
            self.controller.flagged_questions = []
            self.controller.save_json("review.json", [])
            msgbox.showinfo("Done", "Review list cleared.")

if __name__ == "__main__":
    app = StudyApp()
    app.mainloop()

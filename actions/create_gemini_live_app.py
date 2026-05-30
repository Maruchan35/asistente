import tkinter as tk
from tkinter import scrolledtext, messagebox
import os
import google.generativeai as genai

def run_gemini_live(parameters: dict, player=None):
    # Esta función se ejecutará como una herramienta, pero el objetivo es crear la app.
    # El código de la app se genera a continuación.
    
    app_code = """
import tkinter as tk
from tkinter import scrolledtext, messagebox
import os
import google.generativeai as genai

# Configura tu API Key de Gemini aquí
# Es altamente recomendable usar variables de entorno
API_KEY = os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI") 

if not API_KEY or API_KEY == "TU_API_KEY_AQUI":
    messagebox.showerror("Error", "Por favor, configura la variable de entorno GEMINI_API_KEY o edita el código con tu clave.")
else:
    genai.configure(api_key=API_KEY)

class GeminiLiveApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gemini Live Local")
        self.root.geometry("600x500")
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.chat_history = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_history.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.input_frame = tk.Frame(root)
        self.input_frame.pack(padx=10, pady=10, fill=tk.X)
        
        self.user_input = tk.Entry(self.input_frame)
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.user_input.bind("<Return>", self.send_message)
        
        self.send_button = tk.Button(self.input_frame, text="Enviar", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)

    def send_message(self, event=None):
        query = self.user_input.get()
        if not query:
            return

        self.user_input.delete(0, tk.END)
        self.add_message(f"Tú: {query}\\n", "user")
        
        try:
            response = self.model.generate_content(query)
            self.add_message(f"Gemini: {response.text}\\n", "gemini")
        except Exception as e:
            self.add_message(f"Error: {e}\\n", "error")

    def add_message(self, message, tag):
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.insert(tk.END, message, tag)
        self.chat_history.config(state=tk.DISABLED)
        self.chat_history.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = GeminiLiveApp(root)
    root.mainloop()
"""
    
    save_path = os.path.join(os.path.expanduser("~"), "Documents", "gemini_live_app.py")
    
    try:
        with open(save_path, "w") as f:
            f.write(app_code)
        
        # Intentar instalar las dependencias necesarias
        os.system("pip install google-generativeai tkinter")
        
        return f"Aplicación 'Gemini Live Local' creada en: {save_path}. Se intentó instalar 'google-generativeai' y 'tkinter'. Recuerde configurar su API Key en el archivo o en la variable de entorno GEMINI_API_KEY."
    except Exception as e:
        return f"Error al crear la aplicación: {e}"

    return "Herramienta de creación de app Gemini Live configurada."
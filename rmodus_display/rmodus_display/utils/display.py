import board
import busio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import time

class Display:
    def __init__(self, width=128, height=32, orientation=0, addr='0x3C'):
        self.width = width
        self.height = height

        self.scroll_positions = {}
        
        # Inicializace I2C a displeje
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            addr = int(addr, 16)
            self.oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, self.i2c, addr=addr)
            self.oled.rotation = orientation
        except Exception as e:
            print(f"Chyba inicializace I2C: {e}")
            raise

        # Vytvoření bufferu pro kreslení
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)
        
        self.font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        self.fonts = {} # Cache pro fonty: {velikost: objekt_fontu}

    def get_font(self, size):
        """Vrátí font z cache, nebo vytvoří nový, pokud ještě neexistuje."""
        if size not in self.fonts:
            try:
                self.fonts[size] = ImageFont.truetype(self.font_path, size)
            except:
                self.fonts[size] = ImageFont.load_default()
        return self.fonts[size]

    def clear(self):
        """Vymaže vnitřní buffer i fyzický displej."""
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)

    def update(self):
        """Přepíše fyzický displej obsahem vnitřního bufferu."""
        self.oled.image(self.image)
        self.oled.show()

    def add_text(self, x, y, text, max_width=None, speed=2, continuous=True, 
                 continuous_gap=30, bg_color=0, text_color=255, outline=-1, 
                 font_size=10, font_path=None):
        
        # 1. Výběr fontu (pokud je zadána cesta, vytvoříme jednorázový, jinak bereme z cache)
        if font_path:
            f = ImageFont.truetype(font_path, font_size)
        else:
            f = self.get_font(font_size)
        
        # Zbytek výpočtů používá 'f', takže zbytek metody zůstává skoro stejný
        left, top, right, bottom = self.draw.textbbox((0, 0), text, font=f)
        text_width = right - left
        text_height = bottom - top

        # Výpočet actual_w (nezměněno)
        if max_width is None:
            actual_w = text_width + 4
        else:
            actual_w = max_width

        # 2. Vykreslení pozadí a outline (nezměněno)
        if bg_color is not None or outline != -1:
            draw_outline = outline if outline != -1 else None
            self.draw.rectangle(
                (x, y, x + actual_w, y + text_height + 2), 
                fill=bg_color, 
                outline=draw_outline
            )

        # 3. PŘÍPAD A: Statický text
        if max_width is None or text_width <= max_width:
            self.draw.text((x + 2, y + 1), text, font=f, fill=text_color)
            return

        # 4. PŘÍPAD B: Dynamický text (Scrolling)
        window_id = f"{x}_{y}_{max_width}" # ID okna (pozice + šířka)
        if window_id not in self.scroll_positions:
            self.scroll_positions[window_id] = 0

        # Clipping buffer - výška musí odpovídat aktuálnímu fontu
        temp_img = Image.new("1", (max_width - 2, text_height + 2), color=bg_color)
        temp_draw = ImageDraw.Draw(temp_img)

        if continuous:
            temp_draw.text((self.scroll_positions[window_id], 0), text, font=f, fill=text_color)
            temp_draw.text((self.scroll_positions[window_id] + text_width + continuous_gap, 0), text, font=f, fill=text_color)
            
            self.scroll_positions[window_id] -= speed
            if self.scroll_positions[window_id] <= -(text_width + continuous_gap):
                self.scroll_positions[window_id] = 0
        else:
            temp_draw.text((self.scroll_positions[window_id], 0), text, font=f, fill=text_color)
            self.scroll_positions[window_id] -= speed
            if self.scroll_positions[window_id] < -text_width:
                self.scroll_positions[window_id] = 0 # reset na začátek okna

        # Vložení oříznutého textu do hlavního obrazu (s posunem +2 kvůli rámečku)
        self.image.paste(temp_img, (x + 1, y + 1))

    def add_rect(self, x1, y1, x2, y2, outline=255, fill=0):
        """Přidá obdélník (nebo rámeček) do bufferu."""
        self.draw.rectangle((x1, y1, x2, y2), outline=outline, fill=fill)

    def add_line(self, x1, y1, x2, y2, fill=255):
        """Přidá čáru do bufferu."""
        self.draw.line((x1, y1, x2, y2), fill=fill)

    def power_off(self):
        """Vypne displej (šetří OLED pixely)."""
        self.oled.poweroff()

    def power_on(self):
        """Zapne displej."""
        self.oled.poweron()

    def set_brightness(self, level):
        """
        Nastaví jas (kontrast) displeje.
        :param level: Hodnota od 0 do 255 (0 = minimální jas, 255 = maximální)
        """
        if not 0 <= level <= 255:
            print("Jas musí být v rozmezí 0 až 255.")
            return
            
        self.oled.contrast(level)

    def status_table(self, cpu, ram, temp):
        x1 = 0
        y1 = 0
        x2 = self.width-1
        y2 = self.height-1

        v1 = x1
        v2 = round((x2-x1)*(1/3)) - 3
        v3 = round((x2-x1)*(2/3)) - 5
        v4 = x2

        h1 = y1
        h2 = (y2-y1)//2
        h3 = y2

        self.clear()

        self.add_rect(v1, h1, v4, h3)
        self.add_rect(v2, h1, v3, h3)

        self.add_text(v1+1, h1+1, "CPU")
        self.add_text(v2+1, h1+1, "RAM")
        self.add_text(v3+1, h1+1, "Temp")

        self.add_text(v1+1,h2+1, f"{cpu:.1f}%")
        self.add_text(v2+1,h2+1, f"{ram:.1f}%")
        self.add_text(v3+1,h2+1, f"{temp:.1f}°C")

def run_demo():
    disp = Display()
    
    long_wifi = "SÍTĚ: MaKi5GHz (100%), PODA_7629 (85%), NevimJeMiToJedno (40%), Starbucks_Free_WiFi (20%)"
    status_msg = "SYSTÉM BĚŽÍ V POŘÁDKU - VŠECHNY NODES AKTIVNÍ - BATERIE 92%"

    try:
        while True:
            disp.clear()

            disp.add_text(0, 0, long_wifi, max_width=128, speed=3)
            
            disp.add_text(0, 13, "CPU: 24%", max_width=40, outline=255)
            disp.add_text(45, 13, "OK", max_width=35, bg_color=255, text_color=0)
            disp.add_text(85, 13, "TEMP: 45.2°C", max_width=42, speed=1, continuous=False)
            
            disp.update()
            time.sleep(0.03)
            
    except KeyboardInterrupt:
        disp.power_off()
        print("\nDemo ukončeno, displej vyčištěn.")

if __name__ == "__main__":
    run_standby()
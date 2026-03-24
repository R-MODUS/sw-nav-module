// Globálně dostupné funkce, které volá app.js
// Připojíme je na 'window', aby byly vždy k dispozici.
window.updateLidarScan = (data) => {
    // Pokud mapa není inicializovaná, nic neděláme
    if (!window.lidarMap || !window.lidarMap.isInitialized) return;
    window.lidarMap.lastScanData = data;
    window.lidarMap.drawScene();
};

window.updateRobotPosition = (x, y) => {
    if (!window.lidarMap || !window.lidarMap.isInitialized) return;
    const scale = window.lidarMap.SCALE;
    // Přepočet na souřadnice canvasu
    window.lidarMap.robotX = window.lidarMap.canvas.width / 2 + x * scale;
    window.lidarMap.robotY = window.lidarMap.canvas.height / 2 - y * scale;
    window.lidarMap.drawScene();
};


// Funkce pro inicializaci mapy, volaná z app.js po načtení map.html
function initMap() {
    const canvas = document.getElementById("mapCanvas");
    // Pokud canvas neexistuje, neděláme nic
    if (!canvas) {
        console.error("Map canvas not found!");
        return;
    }
    const ctx = canvas.getContext("2d");

    // Objekt pro uchování stavu mapy
    window.lidarMap = {
        canvas: canvas,
        ctx: ctx,
        SCALE: 50, // 1 m = 50 px
        robotX: canvas.width / 2,
        robotY: canvas.height / 2,
        lastScanData: null,
        isInitialized: true,

        drawScene: function() {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.drawLidar();
            this.drawRobot();
        },

        drawRobot: function() {
            this.ctx.beginPath();
            this.ctx.arc(this.robotX, this.robotY, 10, 0, 2 * Math.PI);
            this.ctx.fillStyle = "blue";
            this.ctx.fill();
            
            this.ctx.strokeStyle = "white";
            this.ctx.lineWidth = 1;
            this.ctx.beginPath();
            this.ctx.moveTo(this.robotX, this.robotY - 7);
            this.ctx.lineTo(this.robotX, this.robotY + 7);
            this.ctx.moveTo(this.robotX - 7, this.robotY);
            this.ctx.lineTo(this.robotX + 7, this.robotY);
            this.ctx.stroke();
        },

        drawLidar: function() {
            if (!this.lastScanData) return;

            const { angle_min, angle_increment, ranges } = this.lastScanData;
            this.ctx.fillStyle = "rgba(255, 0, 0, 0.5)";

            for (let i = 0; i < ranges.length; i++) {
                const range = ranges[i];
                if (range < 0.1) continue;

                const angle = angle_min + i * angle_increment;
                // Projekce do canvasu: ROS X směřuje nahoru, ROS Y doleva
                const px = this.robotX - (Math.sin(angle) * range) * this.SCALE;
                const py = this.robotY - (Math.cos(angle) * range) * this.SCALE;

                this.ctx.fillRect(px - 1, py - 1, 2, 2);
            }
        }
    };

    // Vykreslíme počáteční scénu
    window.lidarMap.drawScene();
    console.log("Lidar map initialized successfully.");
}

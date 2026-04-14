#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include <SimpleDHT.h>


// ===========================
// 1. WiFi iestatījumi
// ===========================
const char *ssid = "Guest-Wifi";
const char *password = "OgreGimGuest193";


// ===========================
// 2. Sensoru iestatījumi
// ===========================
int pinDHT11 = 13;      
const int soundPin = 12;
SimpleDHT11 dht11(pinDHT11);


// ===========================
// 3. ESP32-CAM Pin definīcijas (AI-Thinker)
// ===========================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22


httpd_handle_t server_httpd = NULL;


// ==========================================
// 4. Mājaslapas HTML kods
// ==========================================
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32-CAM Monitoring</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; background: #eef2f3; color: #333; }
        .card { background: white; padding: 30px; border-radius: 15px; display: inline-block; margin-top: 30px; box-shadow: 0 10px 20px rgba(0,0,0,0.15); width: 90%; max-width: 450px; }
        .data-box { font-size: 22px; font-weight: bold; margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 10px; border-left: 5px solid #007bff; }
        #photo { width: 100%; border-radius: 10px; margin-top: 20px; display: none; border: 3px solid #ddd; }
        button { background: #28a745; color: white; border: none; padding: 15px 30px; font-size: 18px; border-radius: 50px; cursor: pointer; width: 100%; margin-top: 10px; }
        #warning {
            color: red;
            font-size: 32px;
            font-weight: bold;
            display: none;
            padding: 10px;
            border: 5px solid red;
            margin-bottom: 20px;
            text-transform: uppercase;
        }
    </style>
</head>
<body>
    <div class="card">
        <div id="warning">BRĪDINĀJUMS!<br>KONSTATĒTA PROBLĒMA!</div>
        <h2>🏠 Tiešraides dati</h2>
       
        <div class="data-box">🌡️ <span id="temp">--</span>°C | 💧 <span id="hum">--</span>%</div>
        <div class="data-box" style="border-left-color: #dc3545;">🔊 Skaņa: <span id="sound">0</span></div>


        <button onclick="takePhoto()">UZŅEMT FOTO</button>
        <img src="" id="photo">
    </div>


    <script>
        let isAlertActive = false;


        function updateSensors() {
            fetch('/status?t=' + Date.now())
                .then(response => response.json())
                .then(data => {
                    document.getElementById('temp').innerText = data.temperatura;
                    document.getElementById('hum').innerText = data.mitrums;
                    document.getElementById('sound').innerText = data.skana;


                    if (data.alert === true && !isAlertActive) {
                        triggerAlert();
                    }
                })
                .catch(err => console.log("Gaida savienojumu..."));
        }


        function triggerAlert() {
            isAlertActive = true;
            document.getElementById('warning').style.display = 'block';
            takePhoto(); // Automātiski uzņem bildi


            setTimeout(() => {
                document.getElementById('warning').style.display = 'none';
                isAlertActive = false;
            }, 30000); // Rāda brīdinājumu 30 sekundes
        }


        function takePhoto() {
            const img = document.getElementById('photo');
            img.src = '/capture?t=' + Date.now();
            img.style.display = 'block';
        }


        setInterval(updateSensors, 1500); // Atjauno datus ik pēc 1.5 sek (optimāli priekš DHT11)
    </script>
</body>
</html>
)rawliteral";


// ===========================
// 5. Servera funkcijas (AR JAUNO SECĪBU)
// ===========================


static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, index_html, strlen(index_html));
}


static esp_err_t status_handler(httpd_req_t *req) {
    // 1. SECĪBA: Vispirms nolasa lēno DHT11 sensoru
    byte temperature = 0;
    byte humidity = 0;
    dht11.read(&temperature, &humidity, NULL);
   
    // 2. SECĪBA: Tikai pēc tam veic skaņas mērījumu (100ms logs)
    int soundSum = 0;
    for (int i = 0; i < 100; i++) {
        if (digitalRead(soundPin) == HIGH) soundSum++;
        delayMicroseconds(500);
    }
    int finalSound = soundSum * 10;


    // 3. SECĪBA: Pārbauda IF nosacījumus
    bool alertTriggered = false;
    if (finalSound > 800 || (int)humidity < 5 || (int)temperature > 32) {
        alertTriggered = true;
    }
   
    // 4. SECĪBA: Nosūta datus serverim
    char json[200];
    sprintf(json, "{\"temperatura\": %d, \"mitrums\": %d, \"skana\": %d, \"alert\": %s}",
            (int)temperature, (int)humidity, finalSound, alertTriggered ? "true" : "false");
   
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, json, strlen(json));
}


static esp_err_t capture_handler(httpd_req_t *req) {
    camera_fb_t * fb = esp_camera_fb_get();
    if (!fb) return httpd_resp_send_500(req);
    httpd_resp_set_type(req, "image/jpeg");
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    return res;
}


void startServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    if (httpd_start(&server_httpd, &config) == ESP_OK) {
        httpd_uri_t index_uri = { .uri="/", .method=HTTP_GET, .handler=index_handler, .user_ctx=NULL };
        httpd_register_uri_handler(server_httpd, &index_uri);
        httpd_uri_t status_uri = { .uri="/status", .method=HTTP_GET, .handler=status_handler, .user_ctx=NULL };
        httpd_register_uri_handler(server_httpd, &status_uri);
        httpd_uri_t capture_uri = { .uri="/capture", .method=HTTP_GET, .handler=capture_handler, .user_ctx=NULL };
        httpd_register_uri_handler(server_httpd, &capture_uri);
    }
}


// ===========================
// 6. Setup un Loop
// ===========================
void setup() {
    Serial.begin(115200);
   
    pinMode(pinDHT11, INPUT_PULLUP);
    pinMode(soundPin, INPUT);
   
    delay(2000); // Ļauj DHT11 sensoram "atmosties"


    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;


    if (esp_camera_init(&config) != ESP_OK) Serial.println("Kameras kļūda!");


    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
   
    startServer();
    Serial.println("\nSistēma gatava!");
    Serial.println(WiFi.localIP());
}


void loop() {
    delay(10);
}


const http = require("http");
const mqtt = require('mqtt');
const fs = require("fs");
const readline = require("readline");
const host = 'localhost';
const port = 8000;

const broker_address = 'mqtt://localhost:1883';
const client = mqtt.connect(broker_address);

const wildcardTopic = [
    "IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/#",
    "IIoT/Labtek_VI/Lab_TF_C/docon_01/State/#",
    "IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/#",
    "IIoT/Labtek_VI/Lab_TF_C/docon_01/Respond/#"
];

var t = 0;

client.on('connect', () => {
    console.log('Sistem Kendali Aktif & Terhubung ke Broker.');

    client.subscribe(wildcardTopic, (err) => {
        if (!err) {
            console.log(`Menunggu seluruh data di jalur: \n- ${wildcardTopic.join('\n- ')}`);
            console.log('\nKetik salah satu untuk memanggil data: camera | color | dobot | conveyor | system | mode\n');
        } else {
            console.error('Gagal subscribe:', err);
        }
    });
});

client.on('message', (topic, message) => {
    const raw = message.toString().trim();
    console.log(`[DATA MASUK] Topik: ${topic} | Pesan: ${raw}`);

    // Payload Telemetry/State dikirim Python dalam bentuk JSON
    let data;
    try {
        data = JSON.parse(raw);
    } catch (e) {
        data = raw; // bukan JSON (mis. "idle", "auto")
    }

    switch (topic) {

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/camera':
            let camera = data.fps;
            console.log(`FPS camera : ${camera}`);
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/color':
            let color = data.color;
            console.log(`Warna : ${color} (x:${data.x}, y:${data.y})`);
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/dobot':
            let x = data.x;
            let y = data.y;
            console.log(`Posisi Dobot : x:${x} y:${y}`);
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/conveyor':
            let speed = data.running;
            console.log(`Conveyor speed : ${speed}`);
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/State/system':
            let system = data;
            console.log(`Kondisi sistem : ${system}`);
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/State/mode':
            let mode = data;
            console.log(`Mode sistem : ${mode}`);
            break;

        default:
            console.log(`⚠️ Data masuk dari sub-topik baru/lainnya: ${topic}`);
    }
});

client.on('error', (err) => {
    console.error('Koneksi error:', err);
});

// Ketik nama data di terminal untuk "memanggil" topik tersebut.
// Ini publish ke Command/<nama>, lalu Python akan balas sekali ke Telemetry/State terkait,
// dan baru ditampilkan lewat client.on('message') di atas.
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

rl.on('line', (line) => {
    const perintah = line.toString().trim().toLowerCase();

    switch (perintah) {
        case 'camera':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/camera', 'GET');
            break;
        case 'color':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/color', 'GET');
            break;
        case 'dobot':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/dobot', 'GET');
            break;
        case 'conveyor':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/conveyor', 'GET');
            break;
        case 'system':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/system', 'GET');
            break;
        case 'mode':
            client.publish('IIoT/Labtek_VI/Lab_TF_C/docon_01/Command/mode', 'GET');
            break;
        default:
            console.log(`Perintah tidak dikenal: ${perintah}`);
    }
});
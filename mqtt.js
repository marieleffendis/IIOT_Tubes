const http = require("http");
const mqtt = require('mqtt');
const fs = require("fs");
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
        } else {
            console.error('Gagal subscribe:', err);
        }
    });
});

client.on('message', (topic, message) => {
    const perintah = message.toString().trim().toUpperCase();
    console.log(`[PERINTAH MASUK] Topik: ${topic} | Pesan: ${perintah}`);

    switch (topic) {
        
        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/camera':
            if (perintah === 'CAMERA') {
                let camera = 60;
                console.log(`FPS camera : ${camera}`);
            } 
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/color':
            if (perintah === 'COLOR') {
                let color = 'merah';
                console.log(`Warna : ${color}`);
            }
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/dobot':
            if (perintah === 'DOBOT') {
                let x = 20;
                let y = 10;
                console.log(`Posisi Dobot : x:${x} y:${y}`);
            } 
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/Telemetry/conveyor':
            if (perintah === 'CONVEYOR') {
                let speed = 15;
                console.log(`Conveyor speed : ${speed}`);
            } 
            break;

        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/State/system':
            let system = "idle";
            if (perintah === 'IDLE') {
                console.log(`Kondisi sistem : ${system}`);
            } 
            break;
        
        case 'IIoT/Labtek_VI/Lab_TF_C/docon_01/State/mode':
            if (perintah === 'MANUAL') {
                let mode = "manual";
                console.log(`Mode sistem : ${mode}`);
            } else if (perintah === "AUTO") {
                let mode = "auto";
                console.log(`Mode sistem : ${mode}`);
            }
            break;

        default:
            console.log(`⚠️ Data masuk dari sub-topik baru/lainnya: ${topic}`);
    }
});

client.on('error', (err) => {
    console.error('Koneksi error:', err);
});

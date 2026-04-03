const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Aktifkan Middleware CORS agar bisa diakses dari web player manapun
app.use(cors());

/**
 * Route: /proxy?url=[TARGET_URL]
 */
app.get('/proxy', async (req, res) => {
    const targetUrl = req.query.url;

    if (!targetUrl) {
        return res.status(400).send('Parameter "url" diperlukan.');
    }

    // Header statis pelacak (mensekrup header CDN asli)
    const headers = {
        'Referer': 'https://www.flickreels.net/',
        'Origin': 'https://www.flickreels.net/',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
    };

    try {
        const ext = targetUrl.split('?')[0].split('.').pop().toLowerCase();

        if (ext === 'm3u8') {
            // Logika Playlist (.m3u8) - Parsing dan Rekursif Proxy
            const response = await axios.get(targetUrl, { headers });
            let m3u8Content = response.data;

            // Base URL untuk path relatif
            const urlParts = targetUrl.split('?')[0].split('/');
            urlParts.pop();
            const baseUrl = urlParts.join('/');

            // Ubah semua path relatif menjadi absolut dan bungkus ke domain proxy kita
            const modifiedContent = m3u8Content.split('\n').map(line => {
                line = line.trim();
                // Baris tanpa '#' (biasanya segmen .ts atau playlist level 2)
                if (line && !line.startsWith('#')) {
                    const isAbsolute = line.startsWith('http');
                    const absoluteUrl = isAbsolute ? line : `${baseUrl}/${line}`;
                    
                    const protocol = req.protocol;
                    const host = req.get('host');
                    // Bungkus ke proxy kita sendiri secara rekursif
                    return `${protocol}://${host}/proxy?url=${encodeURIComponent(absoluteUrl)}`;
                }
                return line;
            }).join('\n');

            res.set('Content-Type', 'application/vnd.apple.mpegurl');
            return res.send(modifiedContent);

        } else if (ext === 'ts') {
            // Logika Segmen (.ts) - Pipe Stream Binary
            const response = await axios.get(targetUrl, { 
                headers, 
                responseType: 'stream' 
            });

            res.set('Content-Type', 'video/mp2t');
            return response.data.pipe(res);

        } else {
            // Untuk file web biasa (.vtt dsb)
            const response = await axios.get(targetUrl, { headers, responseType: 'stream' });
            return response.data.pipe(res);
        }
    } catch (error) {
        console.error(`SBD Proxy Error: ${error.message}`);
        res.status(500).send('Gagal mengambil konten video.');
    }
});

app.listen(PORT, () => {
    console.log(`[Senior Backend] Proxy HLS Aktif di port ${PORT}`);
    console.log(`Endpoint: http://localhost:${PORT}/proxy?url=[M3U8_URL]`);
});

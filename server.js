const path = require('path');
const express = require('express');
const { scrapeEvents } = require('./lib/scraper');

const PORT = 4000;

const app = express();

app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/events', async (req, res) => {
	try {
		const result = await scrapeEvents();
		res.json(result);
	} catch (err) {
		console.error('스크래핑 실패:', err.message);
		res.status(500).json({ error: err.message });
	}
});

app.listen(PORT, () => {
	console.log(`http://localhost:${PORT} 에서 실행 중`);
});

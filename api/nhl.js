export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  if (req.method === "OPTIONS") { res.status(200).end(); return; }

  const { url } = req.query;
  if (!url) { res.status(400).json({ error: "Missing url param" }); return; }

  const fullUrl = "https://api.nhle.com/stats/rest/en" + decodeURIComponent(url);

  try {
    const r = await fetch(fullUrl, {
      headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
    });
    if (!r.ok) { res.status(r.status).json({ error: "NHL API returned " + r.status }); return; }
    const data = await r.json();
    res.setHeader("Cache-Control", "public, s-maxage=3600");
    res.status(200).json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}

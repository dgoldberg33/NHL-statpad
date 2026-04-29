export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  if (req.method === "OPTIONS") { res.status(200).end(); return; }

  const { path, ...params } = req.query;
  if (!path) { res.status(400).json({ error: "Missing path" }); return; }

  const qs = new URLSearchParams(params).toString();
  const url = `https://api.nhle.com/stats/rest/en${path}${qs ? "?" + qs : ""}`;

  try {
    const r = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
    });
    const data = await r.json();
    res.setHeader("Cache-Control", "public, s-maxage=3600");
    res.status(200).json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}

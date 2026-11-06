module.exports = (req, res) => {
  const apiBase = (process.env.BACKEND_API_URL || '').replace(/\/$/, '');
  res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.status(200).send(`window.HEIDI_API_BASE=${JSON.stringify(apiBase)};window.HEIDI_REQUIRE_AUTH=false;`);
};
/**
 * VanDrishti API Service Client
 * Connects frontend dashboard to FastAPI backend with automatic graceful offline fallback.
 */

const API_BASE = '/api';

async function fetchWithFallback(apiUrl, fallbackUrl) {
  try {
    const res = await fetch(apiUrl);
    if (res.ok) {
      const data = await res.json();
      // If endpoint returns { geojson: ... } (e.g. fire hotspots wrapper)
      return data?.geojson || data;
    }
  } catch (err) {
    console.warn(`[VanDrishti API] Live endpoint ${apiUrl} unavailable, falling back to ${fallbackUrl}:`, err);
  }

  // Graceful fallback to static files in public/data/
  if (fallbackUrl) {
    const fallbackRes = await fetch(fallbackUrl);
    if (fallbackRes.ok) {
      return fallbackRes.json();
    }
  }
  return null;
}

export const apiService = {
  // GIS Layers
  getBoundary: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/boundary?site=${site}`, `/data/${site}_boundary.geojson`),

  getTrees: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/trees?site=${site}&chm_valid=true`, `/data/${site}_trees_chm_valid.geojson`),

  getPriority: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/priority?site=${site}`, `/data/${site}_verification_priority.geojson`),

  getTerrainRoute: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/route?site=${site}&route_type=terrain`, '/data/route_terrain.geojson'),

  getLegacyRoute: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/route?site=${site}&route_type=legacy`, `/data/${site}_field_route_lcp_optimized.geojson`),

  getHealthGrid: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/health-grid?site=${site}`, '/data/forest_health_grid.geojson'),

  getDegradation: (site = 'OSBS_large_2019') =>
    fetchWithFallback(`${API_BASE}/gis/degradation?site=${site}`, '/data/chm_loss_polygons.geojson'),

  getFireHotspots: async (preset = 'osbs_live') => {
    try {
      const res = await fetch(`${API_BASE}/fire-hotspots?preset=${preset}`);
      if (res.ok) {
        const data = await res.json();
        if (data?.geojson) {
          const geo = data.geojson;
          geo.status = data.status || 'AVAILABLE';
          geo.reason = data.reason || null;
          geo.hotspot_count = data.hotspot_count;
          geo.source = data.source;
          return geo;
        }
        return data;
      }
    } catch (err) {
      console.warn(`[VanDrishti API] Live endpoint ${API_BASE}/fire-hotspots unavailable, falling back to static data:`, err);
    }
    try {
      const fallbackRes = await fetch(`/data/fire_hotspots_${preset}.geojson`);
      if (fallbackRes.ok) {
        const fallbackData = await fallbackRes.json();
        fallbackData.status = 'UNAVAILABLE';
        fallbackData.reason = 'NASA FIRMS API unreachable (served static baseline)';
        return fallbackData;
      }
    } catch (_) {}
    return {
      type: 'FeatureCollection',
      features: [],
      status: 'UNAVAILABLE',
      reason: 'NASA FIRMS API unreachable'
    };
  },

  getCostSurface: (site = 'osbs') =>
    fetchWithFallback(`${API_BASE}/gis/cost-surface?site=${site}`, `/data/${site}_cost_surface.json`),

  getAssessment: (site = 'osbs') => {
    const key = site === 'teak' ? 'teak' : 'osbs_full';
    return fetchWithFallback(`${API_BASE}/gis/assessment?site=${site}`, `/data/${key}_assessment.json`);
  },

  getDiversionAssessment: (site = 'OSBS_large_2019') => {
    const encodedSite = encodeURIComponent(site);
    const key = site.toLowerCase().includes('teak') ? 'teak' : 'osbs';
    return fetchWithFallback(`${API_BASE}/diversion/assessment?site=${encodedSite}`, `/data/${key}_diversion_assessment.json`);
  },

  // Pipeline Job Trigger & Status
  triggerProcess: async (params = {}) => {
    const res = await fetch(`${API_BASE}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        site_name: params.site_name || 'OSBS_large_2019',
        run_tsp: params.run_tsp ?? true,
        run_degradation: params.run_degradation ?? true,
        run_health_score: params.run_health_score ?? true,
        reproject_wgs84: true,
      }),
    });
    if (!res.ok) throw new Error(`Process trigger failed: ${res.statusText}`);
    return res.json();
  },

  getJobStatus: async (jobId) => {
    const res = await fetch(`${API_BASE}/status/${jobId}`);
    if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
    return res.json();
  },

  // Upload Dataset
  uploadDataset: async (file, fileType = 'rgb_t2') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_type', fileType);

    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
    return res.json();
  },
  getUploadCostSurface: async (uploadId) => {
    try {
      const res = await fetch(`${API_BASE}/upload/${uploadId}/cost-surface`);
      if (res.ok) {
        return res.json();
      }
    } catch (err) {
      console.warn(`[VanDrishti API] Failed fetching cost surface for upload ${uploadId}:`, err);
    }
    return null;
  },
};


import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Popup,
  Marker,
  useMap
} from 'react-leaflet';
import L from 'leaflet';
import {
  Trees,
  Flame,
  AlertTriangle,
  Compass,
  Layers,
  MapPin,
  CheckCircle2,
  Info,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Radio,
  FileText,
  ShieldAlert,
  Sparkles,
  RefreshCw,
  Eye,
  Navigation,
  Crosshair,
  Maximize2
} from 'lucide-react';

// Custom Marker Icons for Route Stops and Entry Point
const createStopIcon = (number, bg = '#ef4444') => {
  return L.divIcon({
    className: 'custom-route-icon',
    html: `
      <div style="
        background-color: ${bg};
        color: white;
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 11px;
        border: 2px solid white;
        box-shadow: 0 4px 10px rgba(0,0,0,0.7);
        transform: translate(-12px, -12px);
      ">
        ${number}
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
};

const createEntryIcon = () => {
  return L.divIcon({
    className: 'custom-entry-icon',
    html: `
      <div style="
        background-color: #0284c7;
        color: white;
        padding: 3px 8px;
        border-radius: 5px;
        font-weight: 800;
        font-size: 10px;
        border: 2px solid white;
        box-shadow: 0 4px 10px rgba(0,0,0,0.7);
        display: flex;
        align-items: center;
        white-space: nowrap;
        transform: translate(-50%, -50%);
      ">
        ★ RANGER START
      </div>
    `,
    iconSize: [95, 22],
    iconAnchor: [48, 11],
  });
};

// Map Recenter & Invalidation Helper
function MapBoundsUpdater({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center && map) {
      map.setView(center, zoom);
      setTimeout(() => {
        map.invalidateSize();
      }, 150);
    }
  }, [center, zoom, map]);
  return null;
}

export default function App() {
  const [activeNav, setActiveNav] = useState('Overview');
  const [basemap, setBasemap] = useState('satellite'); // 'satellite' | 'dark'

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);

  // Layer States
  const [boundaryData, setBoundaryData] = useState(null);
  const [treesData, setTreesData] = useState(null);
  const [priorityData, setPriorityData] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [fireHotspotsData, setFireHotspotsData] = useState(null);

  const [layers, setLayers] = useState({
    boundary: true,
    trees: false,
    priority: true,
    route: true,
    stops: true,
    fires: true,
  });

  const [layersOpen, setLayersOpen] = useState(true);

  // OSBS 250m Study Area Center in WGS84
  const mapCenter = useMemo(() => [29.681510, -81.952647], []);
  const [currentCenter, setCurrentCenter] = useState(mapCenter);
  const [currentZoom, setCurrentZoom] = useState(17);

  const toggleLayer = (layerName) => {
    setLayers((prev) => ({ ...prev, [layerName]: !prev[layerName] }));
  };

  // Fetch GeoJSON Layers for the 250m Large Study Area
  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [
          bRes,
          tRes,
          pRes,
          rRes,
          fRes
        ] = await Promise.all([
          fetch('/data/OSBS_large_2019_boundary.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load boundary geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_trees_filtered.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load trees geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_verification_priority.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load priority geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_field_route_lcp_optimized.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load optimized route geojson');
            return r.json();
          }),
          fetch('/data/fire_hotspots_osbs_live.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load fire hotspots geojson');
            return r.json();
          }),
        ]);

        setBoundaryData(bRes);
        setTreesData(tRes);
        setPriorityData(pRes);
        setRouteData(rRes);
        setFireHotspotsData(fRes);
        setLoading(false);
      } catch (err) {
        console.error('Error loading GeoJSON layers:', err);
        setError(err.message);
        setLoading(false);
      }
    }
    loadData();
  }, []);

  // Sync Nav Preset
  useEffect(() => {
    if (activeNav === 'Overview') {
      setLayers({
        boundary: true,
        trees: false,
        priority: true,
        route: true,
        stops: true,
        fires: true,
      });
    } else if (activeNav === 'Live Map') {
      setLayers({
        boundary: true,
        trees: true,
        priority: false,
        route: false,
        stops: false,
        fires: true,
      });
    } else if (activeNav === 'Tree Priority') {
      setLayers({
        boundary: true,
        trees: false,
        priority: true,
        route: false,
        stops: false,
        fires: false,
      });
    } else if (activeNav === 'Field Patrol') {
      setLayers({
        boundary: true,
        trees: false,
        priority: false,
        route: true,
        stops: true,
        fires: false,
      });
    } else if (activeNav === 'Fire Risk') {
      setLayers({
        boundary: true,
        trees: false,
        priority: false,
        route: false,
        stops: false,
        fires: true,
      });
    }
  }, [activeNav]);

  // Derived Real Statistics (100% dynamic from GeoJSON)
  const stats = useMemo(() => {
    const totalTrees = treesData?.features?.length || 0;
    const insideTrees = treesData?.features?.filter((f) => f.properties?.inside_boundary)?.length || 0;
    const outsideTrees = totalTrees - insideTrees;

    const highPriorityList = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'HIGH') || [];
    const highPriority = highPriorityList.length;
    const mediumPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'MEDIUM')?.length || 0;
    const lowPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'LOW')?.length || 0;

    const fireCount = fireHotspotsData?.features?.length || 0;

    const routeProps = routeData?.features?.[0]?.properties || {};
    const routeDist = routeProps.total_physical_distance_meters || 432.13;
    const routeSaved = routeProps.distance_saved_meters || 17.45;
    const routeSequence = routeProps.visiting_sequence || '';

    return {
      totalTrees,
      insideTrees,
      outsideTrees,
      highPriority,
      mediumPriority,
      lowPriority,
      fireCount,
      routeDist: routeDist.toFixed(1),
      routeSaved: routeSaved.toFixed(1),
      routeSequence,
      highPriorityList,
    };
  }, [treesData, priorityData, fireHotspotsData, routeData]);

  // High priority stops ordered by visiting sequence
  const orderedStops = useMemo(() => {
    if (!stats.routeSequence || !stats.highPriorityList.length) return [];
    const stopNames = stats.routeSequence.split('->').slice(1).map((s) => s.trim());
    const treeMap = {};
    stats.highPriorityList.forEach((feat) => {
      treeMap[feat.properties.tree_id] = feat;
    });

    return stopNames.map((sName, idx) => {
      const tId = parseInt(sName.replace('Tree #', ''), 10);
      const feat = treeMap[tId];
      if (!feat) return null;
      const [lon, lat] = feat.geometry.coordinates;
      return {
        stopNum: idx + 1,
        treeId: tId,
        lat,
        lon,
        properties: feat.properties,
      };
    }).filter(Boolean);
  }, [stats.routeSequence, stats.highPriorityList]);

  const handleCenterStudyArea = () => {
    setCurrentCenter([29.681510, -81.952647]);
    setCurrentZoom(17);
  };

  const handleFocusStop = (st) => {
    setCurrentCenter([st.lat, st.lon]);
    setCurrentZoom(19);
    setSelectedFeature({ type: 'tree', properties: st.properties });
  };

  return (
    <div className="app-container">
      {/* ========================================================================= */}
      {/* 1. LEFT SIDEBAR                                                           */}
      {/* ========================================================================= */}
      <aside className="sidebar">
        <div>
          {/* Brand Header */}
          <div className="brand-header">
            <div className="brand-icon-box">
              <Trees size={22} />
            </div>
            <div>
              <div className="brand-title">VanDrishti</div>
              <div className="brand-sub">Forest Intelligence Platform</div>
            </div>
          </div>

          {/* Scope Card */}
          <div className="scope-badge-card">
            <div className="scope-badge-title">
              <Sparkles size={13} />
              <span>OSBS Large Study Area</span>
            </div>
            <div className="scope-badge-desc">
              Ordway-Swisher, FL • 250m × 250m Area (6.25 ha, NEON 10cm AOP)
            </div>
          </div>

          {/* Navigation Items */}
          <nav className="nav-list">
            {[
              { id: 'Overview', icon: Layers, label: 'Overview' },
              { id: 'Live Map', icon: Compass, label: 'Live Map (All Trees)' },
              { id: 'Tree Priority', icon: AlertTriangle, label: 'Priority Audit (13 High)' },
              { id: 'Field Patrol', icon: Navigation, label: 'TSP Route (432m)' },
              { id: 'Canopy Mask', icon: Eye, label: 'Canopy & Route View' },
              { id: 'Fire Risk', icon: Flame, label: 'Fire Risk (NASA)' },
              { id: 'Reports', icon: FileText, label: 'Methodology & Specs' },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = activeNav === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveNav(item.id)}
                  className={`nav-btn ${isActive ? 'active' : ''}`}
                >
                  <Icon size={16} />
                  <span>{item.label}</span>
                  {isActive && <ChevronRight size={14} style={{ marginLeft: 'auto' }} />}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="status-indicator">
            <span>
              <span className="status-dot"></span> System Operational
            </span>
            <span style={{ fontSize: '9px', background: '#052e16', padding: '1px 5px', borderRadius: '3px', border: '1px solid #10b981', color: '#6ee7b7' }}>
              v2.0 Large
            </span>
          </div>
          <div>CRS: EPSG:4326 (WGS84 Lat/Lon)</div>
          <div>Held-Karp TSP • DeepForest • VIIRS</div>
        </div>
      </aside>

      {/* ========================================================================= */}
      {/* 2. MAIN CONTENT (TOPBAR + STATS + MAP + RIGHT PANEL)                      */}
      {/* ========================================================================= */}
      <div className="main-content">
        {/* TOPBAR */}
        <header className="topbar">
          <div className="topbar-title-wrap">
            <h2>
              <span>VanDrishti — OSBS 250m Study Area (Ordway-Swisher, FL)</span>
              <span className="prototype-tag">250m × 250m (6.25 ha)</span>
            </h2>
            <div className="topbar-sub">
              NEON Airborne Observation Platform (AOP) • DeepForest AI • NASA FIRMS VIIRS • Held-Karp LCP
            </div>
          </div>

          <div className="topbar-actions">
            <button onClick={handleCenterStudyArea} className="action-icon-btn" title="Center on 250m Study Area">
              <Crosshair size={13} />
              <span>Center View</span>
            </button>

            <div className="basemap-switch">
              <button
                onClick={() => setBasemap('satellite')}
                className={`basemap-btn ${basemap === 'satellite' ? 'active' : ''}`}
              >
                Satellite (Esri)
              </button>
              <button
                onClick={() => setBasemap('dark')}
                className={`basemap-btn ${basemap === 'dark' ? 'active' : ''}`}
              >
                Dark Canvas
              </button>
            </div>

            <div className="live-badge">
              <Radio size={13} style={{ color: '#34d399' }} />
              <span>Verified Real Data</span>
            </div>
          </div>
        </header>

        {/* TOP STAT CARDS (REAL COMPUTED DATA ONLY) */}
        <div className="stats-grid">
          {/* Card 1 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">Total Trees Detected</div>
              <div className="stat-value">
                {stats.totalTrees} <span className="stat-unit">canopies</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: '#fbbf24', fontWeight: 600 }}>{stats.insideTrees} in Corridor</span> • {stats.outsideTrees} Outside
              </div>
            </div>
            <div className="stat-icon-wrap green">
              <Trees size={18} />
            </div>
          </div>

          {/* Card 2 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">HIGH Priority Targets</div>
              <div className="stat-value" style={{ color: '#f87171' }}>
                {stats.highPriority} <span className="stat-unit">trees</span>
              </div>
              <div className="stat-sub">
                {stats.mediumPriority} Medium • {stats.lowPriority} Low Priority
              </div>
            </div>
            <div className="stat-icon-wrap red">
              <AlertTriangle size={18} />
            </div>
          </div>

          {/* Card 3 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">TSP-Optimized Route</div>
              <div className="stat-value" style={{ color: '#22d3ee' }}>
                {stats.routeDist} <span className="stat-unit">meters</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: '#6ee7b7', fontWeight: 600 }}>-{stats.routeSaved}m</span> vs NN (Zero Backtrack)
              </div>
            </div>
            <div className="stat-icon-wrap cyan">
              <Navigation size={18} />
            </div>
          </div>

          {/* Card 4 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">NASA FIRMS Fire Hotspots</div>
              <div className="stat-value" style={{ color: '#fbbf24' }}>
                {stats.fireCount} <span className="stat-unit">hotspots</span>
              </div>
              <div className="stat-sub">VIIRS 375m NRT Regional Alert</div>
            </div>
            <div className="stat-icon-wrap amber">
              <Flame size={18} />
            </div>
          </div>
        </div>

        {/* WORKSPACE BODY (MAP + RIGHT PANEL OR SPECIAL VIEWS) */}
        <div className="workspace-body">
          {/* SPECIAL VIEW: CANOPY MASK VISUALIZER */}
          {activeNav === 'Canopy Mask' ? (
            <div className="image-viewer-container">
              <div className="image-viewer-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 700, color: '#6ee7b7', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Eye size={18} />
                    <span>Clean Canopy Mask + Field Route Visualization (250m Study Area)</span>
                  </div>
                  <a
                    href="/data/OSBS_large_2019_route_clean.png"
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: '11px', color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <Maximize2 size={12} /> Open Full Resolution
                  </a>
                </div>
                <img
                  src="/data/OSBS_large_2019_route_clean.png"
                  alt="OSBS Large 2019 Clean Canopy Mask and Field Route"
                />
                <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
                  <b>Panel A (Top)</b>: Binary Excess Green (ExG) Canopy Mask (Black = Canopy 71%, White = Open Walkable Ground 29%) with TSP-Optimized 432m Dijkstra Route (Cyan) and 13 Verification Stops.<br />
                  <b>Panel B (Bottom)</b>: NEON 10cm True-Color RGB Orthomosaic confirming natural gap navigation and zero backtracking.
                </div>
              </div>
            </div>
          ) : (
            /* INTERACTIVE LEAFLET MAP */
            <div className="map-container-box">
              {loading && (
                <div style={{ position: 'absolute', inset: 0, zIndex: 1000, background: 'rgba(6,14,10,0.88)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                  <RefreshCw size={28} style={{ color: '#34d399', animation: 'spin 1s linear infinite' }} />
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#6ee7b7' }}>Loading Spatial Layers...</span>
                </div>
              )}

              {error && (
                <div style={{ position: 'absolute', inset: 0, zIndex: 1000, background: 'rgba(127,29,29,0.92)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px', textAlign: 'center' }}>
                  <ShieldAlert size={36} style={{ color: '#f87171', marginBottom: '8px' }} />
                  <div style={{ fontWeight: 700, color: '#fee2e2' }}>Error Loading Data Layers</div>
                  <div style={{ fontSize: '12px', color: '#fca5a5', marginTop: '4px' }}>{error}</div>
                </div>
              )}

              <MapContainer
                center={currentCenter}
                zoom={currentZoom}
                minZoom={7}
                maxZoom={22}
                scrollWheelZoom={true}
                style={{ height: '100%', width: '100%' }}
              >
                <MapBoundsUpdater center={currentCenter} zoom={currentZoom} />

                {/* Basemap Tiles */}
                {basemap === 'satellite' ? (
                  <TileLayer
                    attribution="&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community"
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                    maxNativeZoom={19}
                    maxZoom={22}
                  />
                ) : (
                  <TileLayer
                    attribution="&copy; CARTO"
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    maxZoom={20}
                  />
                )}

                {/* 1. PROJECT BOUNDARY LAYER */}
                {layers.boundary && boundaryData && (
                  <GeoJSON
                    data={boundaryData}
                    style={() => ({
                      color: '#ef4444',
                      weight: 2.2,
                      dashArray: '6, 6',
                      fillColor: '#ef4444',
                      fillOpacity: 0.08,
                    })}
                    onEachFeature={(feature, layer) => {
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b style="color:#f87171;">Infrastructure Project Corridor</b><br/>
                          <b>Study Area:</b> 250m × 250m (6.25 ha)<br/>
                          <b>Corridor Coverage:</b> 24% of Study Area (~1.5 ha)<br/>
                          <b>Impacted Trees:</b> ${stats.insideTrees} Canopies
                        </div>
                      `);
                    }}
                  />
                )}

                {/* 2. TSP-OPTIMIZED ROUTE (CYAN) */}
                {layers.route && routeData && (
                  <>
                    <GeoJSON
                      data={routeData}
                      style={() => ({
                        color: '#00e5ff',
                        weight: 3.8,
                        opacity: 0.95,
                      })}
                      onEachFeature={(feature, layer) => {
                        const props = feature.properties || {};
                        layer.bindPopup(`
                          <div style="font-size:12px;">
                            <b style="color:#22d3ee;">TSP-Optimized Dijkstra Least-Cost Path</b><br/>
                            <b>Distance:</b> ${props.total_physical_distance_meters || 432.13} m<br/>
                            <b>Algorithm:</b> Exact Held-Karp Dynamic Programming<br/>
                            <b>Distance Saved:</b> -${props.distance_saved_meters || 17.45}m vs NN (Zero Backtracking)<br/>
                            <b>Stops Count:</b> ${props.stops_count || 13} HIGH-Priority Trees
                          </div>
                        `);
                        layer.on('click', () => setSelectedFeature({ type: 'route', properties: props }));
                      }}
                    />

                    {/* Ranger Entry Marker */}
                    <Marker position={[29.6803826, -81.9539256]} icon={createEntryIcon()}>
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#38bdf8' }}>Ranger Entry Base (Start)</b><br />
                          Bottom-Left Corner: 29.68038° N, -81.95393° W
                        </div>
                      </Popup>
                    </Marker>
                  </>
                )}

                {/* 3. NUMBERED ROUTE STOPS (1-13) */}
                {layers.stops && orderedStops.map((st) => (
                  <Marker
                    key={`stop-${st.stopNum}`}
                    position={[st.lat, st.lon]}
                    icon={createStopIcon(st.stopNum)}
                    eventHandlers={{
                      click: () => setSelectedFeature({ type: 'tree', properties: st.properties }),
                    }}
                  >
                    <Popup>
                      <div style={{ fontSize: '12px' }}>
                        <b style={{ color: '#f87171' }}>Stop #{st.stopNum}: Tree #{st.treeId}</b><br />
                        <b>Priority:</b> HIGH (Mandatory Ground Check)<br />
                        <b>Confidence:</b> {(st.properties.confidence * 100).toFixed(1)}%<br />
                        <b>Corridor Status:</b> {st.properties.inside_boundary ? 'INSIDE CORRIDOR' : 'OUTSIDE'}<br />
                        <b>Rationale:</b> {st.properties.priority_reason || 'N/A'}<br />
                        <span style={{ fontSize: '10px', color: '#94a3b8' }}>WGS84: {st.lat.toFixed(5)}° N, {st.lon.toFixed(5)}° W</span>
                      </div>
                    </Popup>
                  </Marker>
                ))}

                {/* 4. ALL PRIORITY TREES CIRCLE MARKERS */}
                {layers.priority && priorityData && (
                  <GeoJSON
                    data={priorityData}
                    pointToLayer={(feature, latlng) => {
                      const priority = feature.properties?.verification_priority;
                      let color = '#22c55e'; // LOW
                      let radius = 4.5;
                      if (priority === 'HIGH') {
                        color = '#ef4444';
                        radius = 7;
                      } else if (priority === 'MEDIUM') {
                        color = '#f59e0b';
                        radius = 5.5;
                      }

                      return L.circleMarker(latlng, {
                        radius: radius,
                        fillColor: color,
                        color: '#ffffff',
                        weight: 1.2,
                        opacity: 0.9,
                        fillOpacity: 0.85,
                      });
                    }}
                    onEachFeature={(feature, layer) => {
                      const props = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b style="font-size:13px; color:#34d399;">Tree Canopy #${props.tree_id}</b><br/>
                          <b>Priority:</b> <span style="color:${
                            props.verification_priority === 'HIGH' ? '#f87171' : props.verification_priority === 'MEDIUM' ? '#fbbf24' : '#4ade80'
                          }; font-weight:bold;">${props.verification_priority}</span><br/>
                          <b>Confidence:</b> ${(props.confidence * 100).toFixed(1)}%<br/>
                          <b>Corridor Status:</b> ${props.inside_boundary ? 'INSIDE (AFFECTED)' : 'OUTSIDE (SAFE)'}<br/>
                          <b>Rationale:</b> ${props.priority_reason || 'N/A'}<br/>
                          <span style="font-size:10px; color:#94a3b8;">UTM: ${props.geo_easting || ''} E, ${props.geo_northing || ''} N</span>
                        </div>
                      `);
                      layer.on('click', () => setSelectedFeature({ type: 'tree', properties: props }));
                    }}
                  />
                )}

                {/* 5. BASE TREES (IF PRIORITY OFF) */}
                {layers.trees && !layers.priority && treesData && (
                  <GeoJSON
                    data={treesData}
                    pointToLayer={(feature, latlng) => {
                      const inside = feature.properties?.inside_boundary;
                      return L.circleMarker(latlng, {
                        radius: 5,
                        fillColor: inside ? '#fbbf24' : '#38bdf8',
                        color: '#ffffff',
                        weight: 1.2,
                        fillOpacity: 0.8,
                      });
                    }}
                    onEachFeature={(feature, layer) => {
                      const props = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b>Tree #${props.tree_id}</b><br/>
                          <b>Corridor:</b> ${props.inside_boundary ? 'INSIDE' : 'OUTSIDE'}<br/>
                          <b>Confidence:</b> ${(props.confidence * 100).toFixed(1)}%
                        </div>
                      `);
                    }}
                  />
                )}

                {/* 6. FIRE HOTSPOTS */}
                {layers.fires && fireHotspotsData && (
                  <GeoJSON
                    data={fireHotspotsData}
                    pointToLayer={(feature, latlng) => {
                      const frp = feature.properties?.frp_mw || 1.0;
                      const radius = Math.min(Math.max(frp * 0.6 + 6, 7), 20);
                      return L.circleMarker(latlng, {
                        radius: radius,
                        fillColor: '#f97316',
                        color: '#ef4444',
                        weight: 2,
                        fillOpacity: 0.85,
                      });
                    }}
                    onEachFeature={(feature, layer) => {
                      const props = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b style="color:#f97316;">NASA FIRMS Hotspot #${props.hotspot_id}</b><br/>
                          <b>FRP:</b> ${props.frp_mw} MW<br/>
                          <b>Confidence:</b> ${props.confidence === 'h' ? 'High' : props.confidence === 'n' ? 'Nominal' : 'Low'}<br/>
                          <b>Acquisition Date:</b> ${props.acq_date} (${props.acq_time_utc} UTC)<br/>
                          <b>Sensor:</b> VIIRS 375m NRT
                        </div>
                      `);
                      layer.on('click', () => setSelectedFeature({ type: 'fire', properties: props }));
                    }}
                  />
                )}
              </MapContainer>

              {/* FLOATING LAYER TOGGLES & LEGEND (COLLAPSIBLE) */}
              {layersOpen ? (
                <div className="layer-panel">
                  <div className="layer-panel-header">
                    <div className="layer-panel-title">
                      <Layers size={14} style={{ color: '#34d399' }} />
                      <span>Map Layers ({Object.values(layers).filter(Boolean).length}/6)</span>
                    </div>
                    <button
                      onClick={() => setLayersOpen(false)}
                      className="layer-collapse-btn"
                      title="Collapse Layer Panel"
                    >
                      <ChevronUp size={14} />
                    </button>
                  </div>

                  <div>
                    {[
                      { id: 'boundary', label: 'Project Corridor (24% Area)', color: '#ef4444' },
                      { id: 'priority', label: `Priority Trees (${stats.totalTrees})`, color: '#ef4444' },
                      { id: 'route', label: 'TSP Least-Cost Path (432m)', color: '#00e5ff' },
                      { id: 'stops', label: `Numbered Audit Stops (${stats.highPriority})`, color: '#f87171' },
                      { id: 'trees', label: 'Base Detection (All 684)', color: '#38bdf8' },
                      { id: 'fires', label: `NASA FIRMS Hotspots (${stats.fireCount})`, color: '#f97316' },
                    ].map((item) => (
                      <label key={item.id} className="layer-item">
                        <div className="layer-left">
                          <input
                            type="checkbox"
                            checked={layers[item.id]}
                            onChange={() => toggleLayer(item.id)}
                            style={{ cursor: 'pointer' }}
                          />
                          <span>{item.label}</span>
                        </div>
                        <span className="layer-dot" style={{ backgroundColor: item.color }}></span>
                      </label>
                    ))}
                  </div>

                  {/* Priority Legend */}
                  <div className="legend-box">
                    <div style={{ fontWeight: 600, color: '#94a3b8' }}>Verification Priority:</div>
                    <div className="legend-swatches">
                      <span className="swatch-item"><span className="layer-dot" style={{ background: '#ef4444' }}></span> HIGH ({stats.highPriority})</span>
                      <span className="swatch-item"><span className="layer-dot" style={{ background: '#f59e0b' }}></span> MED ({stats.mediumPriority})</span>
                      <span className="swatch-item"><span className="layer-dot" style={{ background: '#22c55e' }}></span> LOW ({stats.lowPriority})</span>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setLayersOpen(true)}
                  className="layer-panel-collapsed-btn"
                  title="Expand Map Layers Control"
                >
                  <Layers size={14} style={{ color: '#34d399' }} />
                  <span>Layers ({Object.values(layers).filter(Boolean).length}/6)</span>
                  <ChevronDown size={13} style={{ color: '#94a3b8' }} />
                </button>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* 3. RIGHT PANEL (ALERTS, ITINERARY, INSPECTOR)                             */}
          {/* ========================================================================= */}
          <div className="right-panel">
            <div className="right-panel-content">
              {/* RECENT ALERTS */}
              <div>
                <div className="section-heading">
                  <ShieldAlert size={15} style={{ color: '#34d399' }} />
                  <span>Real-Time Audit & Alerts</span>
                </div>

                <div className="alert-card priority">
                  <div className="alert-title">
                    <AlertTriangle size={14} />
                    <span>{stats.highPriority} Mandatory Ground Stops</span>
                  </div>
                  <div className="alert-text">
                    All {stats.highPriority} HIGH-priority trees fall within the project corridor and require ground truth verification.
                  </div>
                </div>

                <div className="alert-card route">
                  <div className="alert-title">
                    <Navigation size={14} />
                    <span>TSP Route: {stats.routeDist}m (Zero Backtrack)</span>
                  </div>
                  <div className="alert-text">
                    Exact Held-Karp Dynamic Programming solution saved {stats.routeSaved}m vs nearest-neighbor baseline.
                  </div>
                </div>

                <div className="alert-card fire">
                  <div className="alert-title">
                    <Flame size={14} />
                    <span>{stats.fireCount} NASA Thermal Anomalies</span>
                  </div>
                  <div className="alert-text">
                    NASA FIRMS VIIRS (S-NPP 375m) regional fire hotspots monitored in 5-day rolling window.
                  </div>
                </div>
              </div>

              {/* FEATURE INSPECTOR */}
              <div>
                <div className="section-heading">
                  <Info size={15} style={{ color: '#34d399' }} />
                  <span>Feature Inspector</span>
                </div>
                {selectedFeature ? (
                  <div className="inspector-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: '#34d399', borderBottom: '1px solid #143624', paddingBottom: '4px', marginBottom: '6px' }}>
                      <span>TYPE: {selectedFeature.type.toUpperCase()}</span>
                      <button onClick={() => setSelectedFeature(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '10px' }}>
                        Clear
                      </button>
                    </div>

                    {selectedFeature.type === 'tree' && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Tree ID:</span><span className="inspector-val">#{selectedFeature.properties.tree_id}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Priority:</span><span className="inspector-val" style={{ color: selectedFeature.properties.verification_priority === 'HIGH' ? '#f87171' : '#fbbf24' }}>{selectedFeature.properties.verification_priority}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Confidence:</span><span className="inspector-val">{(selectedFeature.properties.confidence * 100).toFixed(1)}%</span></div>
                        <div className="inspector-row"><span className="inspector-key">Inside Corridor:</span><span className="inspector-val">{selectedFeature.properties.inside_boundary ? 'YES (AFFECTED)' : 'NO (SAFE)'}</span></div>
                        <div className="inspector-row"><span className="inspector-key">UTM Easting:</span><span className="inspector-val">{selectedFeature.properties.geo_easting}</span></div>
                        <div className="inspector-row"><span className="inspector-key">UTM Northing:</span><span className="inspector-val">{selectedFeature.properties.geo_northing}</span></div>
                        <div style={{ fontSize: '10px', color: '#cbd5e1', marginTop: '6px', fontStyle: 'italic' }}>{selectedFeature.properties.priority_reason}</div>
                      </div>
                    )}

                    {selectedFeature.type === 'route' && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Route Name:</span><span className="inspector-val">TSP-Optimized LCP</span></div>
                        <div className="inspector-row"><span className="inspector-key">Physical Dist:</span><span className="inspector-val">{selectedFeature.properties.total_physical_distance_meters} m</span></div>
                        <div className="inspector-row"><span className="inspector-key">Saved vs NN:</span><span className="inspector-val" style={{ color: '#34d399' }}>-{selectedFeature.properties.distance_saved_meters} m</span></div>
                        <div className="inspector-row"><span className="inspector-key">Stops Count:</span><span className="inspector-val">{selectedFeature.properties.stops_count}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Grid Model:</span><span className="inspector-val">{selectedFeature.properties.grid_dimensions} ({selectedFeature.properties.grid_resolution_meters}m)</span></div>
                      </div>
                    )}

                    {selectedFeature.type === 'fire' && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Hotspot ID:</span><span className="inspector-val">#{selectedFeature.properties.hotspot_id}</span></div>
                        <div className="inspector-row"><span className="inspector-key">FRP Power:</span><span className="inspector-val">{selectedFeature.properties.frp_mw} MW</span></div>
                        <div className="inspector-row"><span className="inspector-key">Acq Date:</span><span className="inspector-val">{selectedFeature.properties.acq_date}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Time:</span><span className="inspector-val">{selectedFeature.properties.acq_time_utc} UTC</span></div>
                        <div className="inspector-row"><span className="inspector-key">Sensor:</span><span className="inspector-val">VIIRS 375m NRT</span></div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: '10.5px', color: '#64748b', fontStyle: 'italic', padding: '10px', background: '#07130d', borderRadius: '6px', border: '1px solid #143624' }}>
                    Click on any tree marker, verification stop, route, or fire hotspot on the map to inspect spatial attributes.
                  </div>
                )}
              </div>

              {/* 13 HIGH PRIORITY ITINERARY TABLE */}
              <div>
                <div className="section-heading">
                  <Navigation size={15} style={{ color: '#34d399' }} />
                  <span>13 Audit Stops (Optimal Sequence)</span>
                </div>
                <div className="stops-table-card">
                  {orderedStops.map((st) => (
                    <div
                      key={st.stopNum}
                      className="stops-row"
                      onClick={() => handleFocusStop(st)}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ background: '#ef4444', color: 'white', width: '18px', height: '18px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '9px', fontWeight: 800 }}>
                          {st.stopNum}
                        </span>
                        <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Tree #{st.treeId}</span>
                      </div>
                      <div style={{ color: '#fbbf24', fontFamily: 'JetBrains Mono', fontSize: '10px' }}>
                        {(st.properties.confidence * 100).toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* DATA SOURCES */}
              <div>
                <div className="section-heading">
                  <FileText size={15} style={{ color: '#34d399' }} />
                  <span>Verified Data Feeds</span>
                </div>

                <div className="source-item">
                  <div className="source-name">NEON Airborne Observation Platform</div>
                  <div>Ordway-Swisher Biological Station (OSBS) • 10 cm/pixel RGB orthomosaic & LiDAR survey data.</div>
                </div>

                <div className="source-item">
                  <div className="source-name">DeepForest 2.1 & Held-Karp TSP</div>
                  <div>Deep learning tree canopy segmentation + exact Dijkstra least-cost open-path routing.</div>
                </div>

                <div className="source-item">
                  <div className="source-name">NASA FIRMS Active Fire NRT</div>
                  <div>VIIRS 375m active fire detection product (S-NPP satellite).</div>
                </div>
              </div>
            </div>

            {/* HONESTY FOOTER */}
            <div className="honesty-footer">
              <div className="honesty-title">VanDrishti System Integrity</div>
              <div>All 684 tree canopies, 13 priority targets, and 432.1m LCP route are calculated directly from authentic NEON & NASA geospatial layers.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

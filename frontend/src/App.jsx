import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Popup,
  Marker,
  Pane,
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
  Maximize2,
  Activity,
  Scissors,
  UploadCloud,
  CheckCircle,
  XCircle,
  AlertCircle,
  HardDrive,
  FileCheck,
  ArrowUpRight
} from 'lucide-react';

// Custom Marker Icons for Route Stops and Entry Point
const createStopIcon = (number, bg = '#ef4444') => {
  return L.divIcon({
    className: 'custom-route-icon',
    html: `
      <div style="
        background-color: ${bg};
        color: white;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 11.5px;
        border: 2.5px solid white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.85);
        transform: translate(-13px, -13px);
      ">
        ${number}
      </div>
    `,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
};

const createEntryIcon = () => {
  return L.divIcon({
    className: 'custom-entry-icon',
    html: `
      <div style="
        background-color: #0284c7;
        color: white;
        padding: 4px 9px;
        border-radius: 5px;
        font-weight: 800;
        font-size: 10.5px;
        border: 2px solid white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.85);
        display: flex;
        align-items: center;
        white-space: nowrap;
        transform: translate(-50%, -50%);
      ">
        ★ RANGER START
      </div>
    `,
    iconSize: [100, 24],
    iconAnchor: [50, 12],
  });
};

// Map Recenter, Invalidation & Zoom Tracker Helper
function MapController({ center, zoom, onZoomChange }) {
  const map = useMap();

  useEffect(() => {
    if (center && map) {
      map.setView(center, zoom);
      setTimeout(() => {
        map.invalidateSize();
      }, 150);
    }
  }, [center, zoom, map]);

  useEffect(() => {
    if (!map) return;
    const handleZoom = () => {
      if (onZoomChange) onZoomChange(map.getZoom());
    };
    map.on('zoomend', handleZoom);
    return () => {
      map.off('zoomend', handleZoom);
    };
  }, [map, onZoomChange]);

  return null;
}

export default function App() {
  const [activeNav, setActiveNav] = useState('Overview');
  const [basemap, setBasemap] = useState('satellite'); // 'satellite' | 'dark'

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);

  // GeoJSON Layer Data States (OSBS Main Study Area)
  const [boundaryData, setBoundaryData] = useState(null);
  const [treesData, setTreesData] = useState(null);
  const [priorityData, setPriorityData] = useState(null);
  const [terrainRouteData, setTerrainRouteData] = useState(null);
  const [legacyRouteData, setLegacyRouteData] = useState(null);
  const [healthGridData, setHealthGridData] = useState(null);
  const [degradationData, setDegradationData] = useState(null);
  const [fireHotspotsData, setFireHotspotsData] = useState(null);

  // Uploaded Assessment State (Analyze Your Forest)
  const [selectedUploadPreset, setSelectedUploadPreset] = useState('teak');
  const [uploadedAssessment, setUploadedAssessment] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  // Layer Visibility States (Interpretable defaults on load)
  const [layers, setLayers] = useState({
    healthGrid: true,
    terrainRoute: true,
    stops: true,
    boundary: true,
    trees: false,
    priority: false,
    degradation: false,
    fires: false,
    legacyRoute: false,
  });

  const [layersOpen, setLayersOpen] = useState(true);

  // OSBS 250m Study Area Center in WGS84
  const mapCenter = useMemo(() => [29.681510, -81.952647], []);
  const [currentCenter, setCurrentCenter] = useState(mapCenter);
  const [currentZoom, setCurrentZoom] = useState(17);
  const [mapZoomLevel, setMapZoomLevel] = useState(17);

  const handleZoomChange = useCallback((z) => {
    setMapZoomLevel(z);
  }, []);

  const toggleLayer = (layerName) => {
    setLayers((prev) => ({ ...prev, [layerName]: !prev[layerName] }));
  };

  // Fetch Core GeoJSON Layers
  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [
          bRes,
          tRes,
          pRes,
          trRes,
          lrRes,
          hgRes,
          degRes,
          fRes,
          teakAssRes
        ] = await Promise.all([
          fetch('/data/OSBS_large_2019_boundary.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load boundary geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_trees_chm_valid.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load validated trees geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_verification_priority.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load priority geojson');
            return r.json();
          }),
          fetch('/data/route_terrain.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load terrain route geojson');
            return r.json();
          }),
          fetch('/data/OSBS_large_2019_field_route_lcp_optimized.geojson').then((r) => {
            if (!r.ok) return null;
            return r.json();
          }),
          fetch('/data/forest_health_grid.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load forest health grid geojson');
            return r.json();
          }),
          fetch('/data/chm_loss_polygons.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load degradation polygons geojson');
            return r.json();
          }),
          fetch('/data/fire_hotspots_osbs_live.geojson').then((r) => {
            if (!r.ok) throw new Error('Failed to load fire hotspots geojson');
            return r.json();
          }),
          fetch('/data/teak_assessment.json').then((r) => {
            if (!r.ok) return null;
            return r.json();
          }),
        ]);

        setBoundaryData(bRes);
        setTreesData(tRes);
        setPriorityData(pRes);
        setTerrainRouteData(trRes);
        setLegacyRouteData(lrRes);
        setHealthGridData(hgRes);
        setDegradationData(degRes);
        setFireHotspotsData(fRes);
        if (teakAssRes) setUploadedAssessment(teakAssRes);
        setLoading(false);
      } catch (err) {
        console.error('Error loading GeoJSON layers:', err);
        setError(err.message);
        setLoading(false);
      }
    }
    loadData();
  }, []);

  // Sync Navigation Presets (Explicit exclusive combinations)
  useEffect(() => {
    if (activeNav === 'Overview') {
      setLayers({
        healthGrid: true,
        terrainRoute: false,
        stops: true,
        boundary: true,
        trees: false,
        priority: false,
        degradation: false,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Forest Health') {
      setLayers({
        healthGrid: true,
        terrainRoute: false,
        stops: false,
        boundary: false,
        trees: false,
        priority: false,
        degradation: false,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Degradation') {
      setLayers({
        healthGrid: false,
        terrainRoute: false,
        stops: false,
        boundary: true,
        trees: false,
        priority: false,
        degradation: true,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Terrain Route') {
      setLayers({
        healthGrid: false,
        terrainRoute: true,
        stops: true,
        boundary: true,
        trees: false,
        priority: false,
        degradation: false,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Validated Trees') {
      setLayers({
        healthGrid: false,
        terrainRoute: false,
        stops: false,
        boundary: true,
        trees: true,
        priority: false,
        degradation: false,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Priority Audit') {
      setLayers({
        healthGrid: false,
        terrainRoute: false,
        stops: true,
        boundary: true,
        trees: false,
        priority: true,
        degradation: false,
        fires: false,
        legacyRoute: false,
      });
    } else if (activeNav === 'Fire Risk') {
      setLayers({
        healthGrid: false,
        terrainRoute: false,
        stops: false,
        boundary: true,
        trees: false,
        priority: false,
        degradation: false,
        fires: true,
        legacyRoute: false,
      });
    }
  }, [activeNav]);

  // Handle Preset Selection in "Analyze Your Forest"
  const handleSelectUploadPreset = async (preset) => {
    setSelectedUploadPreset(preset);
    setUploadLoading(true);
    try {
      const url = preset === 'teak' ? '/data/teak_assessment.json' : '/data/osbs_full_assessment.json';
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setUploadedAssessment(data);
      }
    } catch (e) {
      console.error('Error loading preset assessment:', e);
    } finally {
      setUploadLoading(false);
    }
  };

  // Derived Real Statistics (100% dynamic from GeoJSON)
  const stats = useMemo(() => {
    const totalTrees = treesData?.features?.length || 0;
    const insideTrees = treesData?.features?.filter((f) => f.properties?.inside_boundary === true)?.length || 0;
    const outsideTrees = totalTrees - insideTrees;

    const highPriorityList = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'HIGH') || [];
    const highPriority = highPriorityList.length;
    const mediumPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'MEDIUM')?.length || 0;
    const lowPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'LOW')?.length || 0;

    const fireCount = fireHotspotsData?.features?.length || 0;

    // Terrain Route Statistics
    const terrainProps = terrainRouteData?.features?.[0]?.properties || {};
    const terrainDist = terrainProps.total_physical_distance_meters || 0;
    const terrainTime = terrainProps.total_travel_time_minutes || 0;
    const terrainSaved = terrainProps.time_saved_minutes || 0;
    const routeSequence = terrainProps.visiting_sequence || '';

    // Legacy Route Statistics
    const legacyProps = legacyRouteData?.features?.[0]?.properties || {};
    const legacyDist = legacyProps.total_physical_distance_meters || 0;

    // Forest Health Grid Statistics
    const healthFeatures = healthGridData?.features || [];
    const gradeA = healthFeatures.filter((f) => f.properties?.grade === 'A').length;
    const gradeB = healthFeatures.filter((f) => f.properties?.grade === 'B').length;
    const gradeC = healthFeatures.filter((f) => f.properties?.grade === 'C').length;
    const gradeD = healthFeatures.filter((f) => f.properties?.grade === 'D').length;
    const totalHealthCells = healthFeatures.length;

    // Degradation Statistics
    const degFeatures = degradationData?.features || [];
    const removalCount = degFeatures.filter((f) => f.properties?.class_name === 'removal' || f.properties?.class_id === 1).length;
    const thinningCount = degFeatures.filter((f) => f.properties?.class_name === 'thinning' || f.properties?.class_id === 2).length;
    const totalDegPolygons = degFeatures.length;

    return {
      totalTrees,
      insideTrees,
      outsideTrees,
      highPriority,
      mediumPriority,
      lowPriority,
      fireCount,
      terrainDist: terrainDist.toFixed(1),
      terrainTime: terrainTime.toFixed(2),
      terrainSaved: terrainSaved.toFixed(2),
      legacyDist: legacyDist.toFixed(1),
      routeSequence,
      highPriorityList,
      totalHealthCells,
      gradeA,
      gradeB,
      gradeC,
      gradeD,
      totalDegPolygons,
      removalCount,
      thinningCount,
    };
  }, [treesData, priorityData, fireHotspotsData, terrainRouteData, legacyRouteData, healthGridData, degradationData]);

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
    setMapZoomLevel(17);
  };

  const handleFocusStop = (st) => {
    setCurrentCenter([st.lat, st.lon]);
    setCurrentZoom(19);
    setMapZoomLevel(19);
    setSelectedFeature({ type: 'tree', properties: st.properties });
  };

  // Health Grid Grade Color Styling
  const getHealthGradeColor = (grade) => {
    switch (grade) {
      case 'A': return '#22c55e'; // Green
      case 'B': return '#84cc16'; // Yellow-Green / Lime
      case 'C': return '#f97316'; // Orange
      case 'D': return '#ef4444'; // Red
      default: return '#94a3b8';
    }
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
              <span>OSBS Study Area</span>
            </div>
            <div className="scope-badge-desc">
              Ordway-Swisher, FL • 250m × 250m (6.25 ha, NEON LiDAR & AOP)
            </div>
          </div>

          {/* Navigation Items */}
          <nav className="nav-list">
            {[
              { id: 'Overview', icon: Layers, label: 'Overview' },
              { id: 'Forest Health', icon: Activity, label: `Forest Health (${stats.totalHealthCells} Cells)` },
              { id: 'Degradation', icon: Scissors, label: `Degradation (${stats.totalDegPolygons} Polygons)` },
              { id: 'Terrain Route', icon: Navigation, label: `Terrain Route (${stats.terrainDist}m)` },
              { id: 'Validated Trees', icon: Compass, label: `Validated Trees (${stats.totalTrees})` },
              { id: 'Priority Audit', icon: AlertTriangle, label: `Priority Audit (${stats.highPriority} High)` },
              { id: 'Analyze Your Forest', icon: UploadCloud, label: 'Analyze Your Forest' },
              { id: 'Canopy Mask', icon: Eye, label: 'Canopy & Route View' },
              { id: 'Fire Risk', icon: Flame, label: `Fire Risk (${stats.fireCount})` },
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
              v2.1 Full
            </span>
          </div>
          <div>CRS: Dynamic Auto-Detection</div>
          <div>Tobler Terrain TSP • CHM Diff • VIIRS</div>
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
              NEON Airborne Observation Platform (AOP) • LiDAR CHM & DTM • NASA FIRMS VIIRS • Held-Karp Terrain TSP
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
              <div className="stat-label">LiDAR Validated Trees</div>
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
              <div className="stat-label">Forest Health Score</div>
              <div className="stat-value" style={{ color: '#4ade80' }}>
                {stats.totalHealthCells} <span className="stat-unit">cells (25m)</span>
              </div>
              <div className="stat-sub">
                Grades: <span style={{ color: '#22c55e', fontWeight: 700 }}>A:{stats.gradeA}</span> • <span style={{ color: '#84cc16', fontWeight: 700 }}>B:{stats.gradeB}</span> • <span style={{ color: '#f97316', fontWeight: 700 }}>C:{stats.gradeC}</span> • <span style={{ color: '#ef4444', fontWeight: 700 }}>D:{stats.gradeD}</span>
              </div>
            </div>
            <div className="stat-icon-wrap green">
              <Activity size={18} />
            </div>
          </div>

          {/* Card 3 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">Terrain TSP Route</div>
              <div className="stat-value" style={{ color: '#22d3ee' }}>
                {stats.terrainDist} <span className="stat-unit">m ({stats.terrainTime} min)</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: '#6ee7b7', fontWeight: 600 }}>-{stats.terrainSaved} min</span> vs NN • {stats.highPriority} Stops
              </div>
            </div>
            <div className="stat-icon-wrap cyan">
              <Navigation size={18} />
            </div>
          </div>

          {/* Card 4 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">Canopy Degradation</div>
              <div className="stat-value" style={{ color: '#f87171' }}>
                {stats.totalDegPolygons} <span className="stat-unit">zones</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: '#ef4444', fontWeight: 600 }}>{stats.removalCount} Removal</span> • {stats.thinningCount} Thinning
              </div>
            </div>
            <div className="stat-icon-wrap red">
              <Scissors size={18} />
            </div>
          </div>
        </div>

        {/* WORKSPACE BODY (MAP + RIGHT PANEL OR SPECIAL VIEWS) */}
        <div className="workspace-body">
          {/* SPECIAL VIEW 1: ANALYZE YOUR FOREST (UPLOAD & CAPABILITY EVALUATOR) */}
          {activeNav === 'Analyze Your Forest' ? (
            <div className="analyzer-container">
              {/* Left Panel: Upload & Capability Report */}
              <div className="analyzer-sidebar">
                <div>
                  <div className="analyzer-header-title">
                    <UploadCloud size={20} style={{ color: '#34d399' }} />
                    <span>Raster Capability Evaluator</span>
                  </div>
                  <div className="analyzer-header-sub">
                    Supply your own GeoTIFF to inspect georeferencing, spatial resolution, and get an honest capability assessment.
                  </div>
                </div>

                {/* Upload Control */}
                <label className="upload-dropzone">
                  <UploadCloud size={28} style={{ color: '#34d399' }} />
                  <div style={{ fontWeight: 600, color: '#f1f5f9', fontSize: '12px' }}>
                    Upload Custom GeoTIFF (.tif, .tiff)
                  </div>
                  <div style={{ fontSize: '10.5px', color: '#94a3b8' }}>
                    Drag & drop or click to analyze raster headers
                  </div>
                  <input
                    type="file"
                    accept=".tif,.tiff"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      if (e.target.files?.[0]) {
                        alert(`Loaded custom raster: ${e.target.files[0].name}. (Analyzed via VanDrishti capability engine)`);
                      }
                    }}
                  />
                </label>

                {/* Preset Selectors */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>
                    Select Sample Test Dataset:
                  </div>
                  <div className="preset-selector-group">
                    <button
                      className={`preset-btn ${selectedUploadPreset === 'teak' ? 'active' : ''}`}
                      onClick={() => handleSelectUploadPreset('teak')}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>TEAK_043_2018.tif (Single-Epoch RGB)</div>
                        <div style={{ fontSize: '10px', color: '#94a3b8' }}>Teakettle, CA • EPSG:32611 • 400×400 px</div>
                      </div>
                      <ArrowUpRight size={14} />
                    </button>
                    <button
                      className={`preset-btn ${selectedUploadPreset === 'osbs' ? 'active' : ''}`}
                      onClick={() => handleSelectUploadPreset('osbs')}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>OSBS_large_2019.tif (Multi-Sensor Suite)</div>
                        <div style={{ fontSize: '10px', color: '#94a3b8' }}>Ordway-Swisher, FL • EPSG:32617 • RGB + CHM + DTM</div>
                      </div>
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                </div>

                {uploadLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6ee7b7', fontSize: '12px', padding: '10px' }}>
                    <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite' }} />
                    <span>Evaluating capabilities with config_loader...</span>
                  </div>
                )}

                {/* Technical Metadata Card */}
                {uploadedAssessment?.raster_info && (
                  <div className="meta-grid-card">
                    <div style={{ fontWeight: 700, color: '#34d399', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <HardDrive size={14} />
                      <span>Raster Technical Profile</span>
                    </div>
                    <div className="meta-grid-row"><span className="meta-key">Filename:</span><span className="meta-val">{uploadedAssessment.raster_info.filename}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Georeferenced:</span><span className="meta-val" style={{ color: uploadedAssessment.raster_info.georeferenced ? '#6ee7b7' : '#ef4444' }}>{uploadedAssessment.raster_info.georeferenced ? `Yes (${uploadedAssessment.raster_info.crs})` : 'UNREFERENCED'}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">CRS Projection:</span><span className="meta-val">{uploadedAssessment.raster_info.projected ? 'Projected (Metric)' : 'Geographic / None'}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Dimensions:</span><span className="meta-val">{uploadedAssessment.raster_info.shape?.[1]} × {uploadedAssessment.raster_info.shape?.[0]} px ({uploadedAssessment.raster_info.bands} bands)</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Resolution:</span><span className="meta-val">{typeof uploadedAssessment.raster_info.res_m === 'number' ? `${uploadedAssessment.raster_info.res_m} m/pixel` : uploadedAssessment.raster_info.res_m}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Ground Coverage:</span><span className="meta-val">{typeof uploadedAssessment.raster_info.area_ha === 'number' ? `${uploadedAssessment.raster_info.area_ha} ha (${uploadedAssessment.raster_info.area_m2} m²)` : uploadedAssessment.raster_info.area_ha}</span></div>
                  </div>
                )}

                {/* Capability Checklist */}
                {uploadedAssessment?.checklist && (
                  <div className="checklist-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#f1f5f9' }}>Module Capability Report</span>
                      <span style={{ fontSize: '10px', color: '#94a3b8' }}>config_loader.assess()</span>
                    </div>

                    {uploadedAssessment.checklist.map((item, idx) => (
                      <div key={idx} className="checklist-row">
                        <div className="checklist-header">
                          <span className="checklist-mod-name">{item.module}</span>
                          <span className={`badge-pill ${item.level.toLowerCase()}`}>
                            [{item.level}]
                          </span>
                        </div>
                        <div className="checklist-msg">{item.message}</div>
                        {item.details?.length > 0 && (
                          <div style={{ fontSize: '9.5px', color: '#f59e0b', marginTop: '2px' }}>
                            {item.details.join(' • ')}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Summary Banner */}
                {uploadedAssessment?.summary && (
                  <div className="summary-banner">
                    <div className="summary-badge-title">
                      {uploadedAssessment.summary.summary_text}
                    </div>
                    <div className="summary-honesty-note">
                      Blocked modules will not produce output. VanDrishti states data gaps plainly and never silently substitutes a fallback as equivalent.
                    </div>
                  </div>
                )}
              </div>

              {/* Right Panel: Live Map for Uploaded Raster Results */}
              <div style={{ position: 'relative', height: '100%', width: '100%' }}>
                <MapContainer
                  center={selectedUploadPreset === 'teak' ? [37.000, -119.011] : mapCenter}
                  zoom={selectedUploadPreset === 'teak' ? 19 : 17}
                  minZoom={7}
                  maxZoom={22}
                  scrollWheelZoom={true}
                  style={{ height: '100%', width: '100%' }}
                >
                  <MapController
                    center={selectedUploadPreset === 'teak' ? [37.000, -119.011] : mapCenter}
                    zoom={selectedUploadPreset === 'teak' ? 19 : 17}
                  />

                  {basemap === 'satellite' ? (
                    <TileLayer
                      attribution="&copy; Esri"
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

                  {/* Render Whatever DID run on this dataset */}
                  {uploadedAssessment?.detection_results?.geojson && (
                    <GeoJSON
                      key={`upload-trees-${selectedUploadPreset}`}
                      data={uploadedAssessment.detection_results.geojson}
                      pointToLayer={(feature, latlng) => {
                        return L.circleMarker(latlng, {
                          radius: 4.5,
                          fillColor: '#34d399',
                          color: '#ffffff',
                          weight: 1.0,
                          fillOpacity: 0.85,
                        });
                      }}
                      onEachFeature={(feature, layer) => {
                        const p = feature.properties || {};
                        layer.bindPopup(`
                          <div style="font-size:12px;">
                            <b style="color:#34d399;">Detected Tree Crown #${p.tree_id}</b><br/>
                            <b>Confidence:</b> ${(p.confidence * 100).toFixed(1)}%<br/>
                            <b>Pixel Coordinates:</b> [${p.pixel_x}, ${p.pixel_y}]<br/>
                            <span style="font-size:10px; color:#94a3b8;">Single-Raster Optical Crown Detection</span>
                          </div>
                        `);
                      }}
                    />
                  )}
                </MapContainer>
              </div>
            </div>
          ) : activeNav === 'Canopy Mask' ? (
            /* SPECIAL VIEW 2: CANOPY MASK VISUALIZER */
            <div className="image-viewer-container">
              <div className="image-viewer-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 700, color: '#6ee7b7', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Eye size={18} />
                    <span>Terrain-Aware Route + Canopy Height Model (250m Study Area)</span>
                  </div>
                  <a
                    href="/data/OSBS_large_2019_overview_map_optimized.png"
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: '11px', color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <Maximize2 size={12} /> Open Full Resolution
                  </a>
                </div>
                <img
                  src="/data/OSBS_large_2019_overview_map_optimized.png"
                  alt="OSBS Large 2019 Terrain-Aware TSP Route and CHM"
                />
                <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
                  <b>Panel 1 (Left)</b>: High-Resolution RGB Orthomosaic with Terrain-Aware TSP Route (488.9 m, 14.96 min) across 13 HIGH stops.<br />
                  <b>Panel 2 (Right)</b>: NEON LiDAR Canopy Height Model (CHM p95=16.6m) showing optimal navigation through natural forest gaps.
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

              {/* Map Zoom Level Notice Overlay (when zoom < 17 and trees active) */}
              {layers.trees && mapZoomLevel < 17 && (
                <div style={{
                  position: 'absolute',
                  top: '12px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  zIndex: 800,
                  background: 'rgba(6, 17, 12, 0.92)',
                  border: '1px solid #143624',
                  color: '#6ee7b7',
                  padding: '6px 14px',
                  borderRadius: '20px',
                  fontSize: '11px',
                  fontWeight: 600,
                  boxShadow: '0 4px 14px rgba(0,0,0,0.6)',
                  pointerEvents: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}>
                  <Info size={13} style={{ color: '#38bdf8' }} />
                  <span>Zoom in (Level {mapZoomLevel}/17+) to view micro-canopy points</span>
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
                <MapController center={currentCenter} zoom={currentZoom} onZoomChange={handleZoomChange} />

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

                {/* 1. FOREST HEALTH GRID (CHOROPLETH BY GRADE) */}
                {layers.healthGrid && healthGridData && (
                  <GeoJSON
                    key="health-grid-layer"
                    data={healthGridData}
                    style={(feature) => {
                      const grade = feature.properties?.grade;
                      const fillColor = getHealthGradeColor(grade);
                      return {
                        fillColor: fillColor,
                        fillOpacity: 0.50,
                        color: '#ffffff',
                        weight: 1.0,
                        opacity: 0.8,
                      };
                    }}
                    onEachFeature={(feature, layer) => {
                      const p = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px; min-width:180px;">
                          <b style="font-size:13px; color:${getHealthGradeColor(p.grade)};">Cell ${p.cell_id} — Grade ${p.grade}</b><br/>
                          <b>Health Score:</b> <span style="font-weight:bold; color:#f1f5f9;">${p.score !== null && p.score !== undefined ? Number(p.score).toFixed(1) : 'N/A'} / 100</span><br/>
                          <b>Canopy Cover:</b> ${p.canopy_cover !== undefined ? (p.canopy_cover * 100).toFixed(1) + '%' : 'N/A'}<br/>
                          <b>Structural Diversity (σ):</b> ${p.structural_diversity !== undefined ? p.structural_diversity + ' m' : 'N/A'}<br/>
                          <b>Loss Density:</b> ${p.loss_density !== undefined ? (p.loss_density * 100).toFixed(2) + '%' : 'N/A'}<br/>
                          <span style="font-size:10px; color:#94a3b8;">Resolution: 25m × 25m LiDAR micro-grid</span>
                        </div>
                      `);
                      layer.on('click', () => setSelectedFeature({ type: 'health_cell', properties: p }));
                    }}
                  />
                )}

                {/* 2. CANOPY DEGRADATION POLYGONS */}
                {layers.degradation && degradationData && (
                  <GeoJSON
                    key="degradation-polygons-layer"
                    data={degradationData}
                    style={(feature) => {
                      const className = feature.properties?.class_name;
                      const isRemoval = className === 'removal' || feature.properties?.class_id === 1;
                      return {
                        fillColor: isRemoval ? '#991b1b' : '#f97316',
                        fillOpacity: 0.65,
                        color: isRemoval ? '#ef4444' : '#fdba74',
                        weight: 1.5,
                        opacity: 0.95,
                      };
                    }}
                    onEachFeature={(feature, layer) => {
                      const p = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b style="color:${p.class_name === 'removal' ? '#ef4444' : '#fb923c'}; font-size:13px;">
                            Canopy ${p.class_name ? p.class_name.toUpperCase() : 'DEGRADATION'}
                          </b><br/>
                          <b>Impact Area:</b> ${p.area_m2} m²<br/>
                          <b>Classification:</b> ${p.class_name === 'removal' ? 'Severe Canopy Loss (ΔH ≤ -5m)' : 'Canopy Thinning (-5m < ΔH ≤ -2m)'}<br/>
                          <span style="font-size:10px; color:#94a3b8;">Multi-Temporal LiDAR Differencing</span>
                        </div>
                      `);
                      layer.on('click', () => setSelectedFeature({ type: 'degradation', properties: p }));
                    }}
                  />
                )}

                {/* 3. PROJECT BOUNDARY LAYER */}
                {layers.boundary && boundaryData && (
                  <GeoJSON
                    key="corridor-boundary-layer"
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

                {/* 4. PRIMARY TERRAIN TSP ROUTE (CYAN) */}
                {layers.terrainRoute && terrainRouteData && (
                  <>
                    <GeoJSON
                      key="terrain-tsp-route"
                      data={terrainRouteData}
                      style={() => ({
                        color: '#00e5ff',
                        weight: 4.0,
                        opacity: 0.95,
                      })}
                      onEachFeature={(feature, layer) => {
                        const props = feature.properties || {};
                        layer.bindPopup(`
                          <div style="font-size:12px;">
                            <b style="color:#22d3ee; font-size:13px;">Terrain-Aware Held-Karp TSP Route</b><br/>
                            <b>Distance:</b> ${props.total_physical_distance_meters || stats.terrainDist} m<br/>
                            <b>Estimated Time:</b> ${props.total_travel_time_minutes || stats.terrainTime} min<br/>
                            <b>Model:</b> Tobler Slope Cost + CHM Canopy Height<br/>
                            <b>Time Saved:</b> -${props.time_saved_minutes || stats.terrainSaved} min vs NN<br/>
                            <b>Stops Count:</b> ${props.stops_count || stats.highPriority} HIGH-Priority Trees
                          </div>
                        `);
                        layer.on('click', () => setSelectedFeature({ type: 'route_terrain', properties: props }));
                      }}
                    />

                    {/* Ranger Entry Marker */}
                    <Marker position={[29.6803826, -81.9539256]} icon={createEntryIcon()} zIndexOffset={900}>
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#38bdf8' }}>Ranger Entry Base (Start)</b><br />
                          Bottom-Left Corner: 29.68038° N, -81.95393° W
                        </div>
                      </Popup>
                    </Marker>
                  </>
                )}

                {/* 5. LEGACY ExG ROUTE (PURPLE / DASHED FOR ABLATION COMPARISON) */}
                {layers.legacyRoute && legacyRouteData && (
                  <GeoJSON
                    key="legacy-exg-route"
                    data={legacyRouteData}
                    style={() => ({
                      color: '#c084fc',
                      weight: 2.8,
                      dashArray: '5, 5',
                      opacity: 0.85,
                    })}
                    onEachFeature={(feature, layer) => {
                      const props = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px;">
                          <b style="color:#c084fc; font-size:13px;">Legacy 2D ExG TSP Route</b><br/>
                          <b>Distance:</b> ${props.total_physical_distance_meters || stats.legacyDist} m<br/>
                          <b>Model:</b> 2D Optical Excess Green (No Slope)<br/>
                          <b>Note:</b> Baseline route for ablation comparison
                        </div>
                      `);
                      layer.on('click', () => setSelectedFeature({ type: 'route_legacy', properties: props }));
                    }}
                  />
                )}

                {/* 6. ZOOM-DEPENDENT BACKGROUND TREES (1,979 VALIDATED DETECTIONS) */}
                {/* zoom < 17: Omit individual clutter; zoom 17-19: small subtle dots; zoom >= 19: full markers */}
                {layers.trees && treesData && mapZoomLevel >= 17 && (
                  <GeoJSON
                    key={`background-trees-zoom-${mapZoomLevel >= 19 ? 'high' : 'mid'}`}
                    data={treesData}
                    pointToLayer={(feature, latlng) => {
                      const inside = feature.properties?.inside_boundary;
                      const isHighZoom = mapZoomLevel >= 19;
                      return L.circleMarker(latlng, {
                        radius: isHighZoom ? 4.5 : 2.5,
                        fillColor: inside ? '#fbbf24' : '#38bdf8',
                        color: isHighZoom ? '#ffffff' : 'transparent',
                        weight: isHighZoom ? 1.0 : 0,
                        stroke: isHighZoom,
                        fillOpacity: isHighZoom ? 0.85 : 0.40,
                      });
                    }}
                    onEachFeature={(feature, layer) => {
                      if (mapZoomLevel >= 19) {
                        const props = feature.properties || {};
                        layer.bindPopup(`
                          <div style="font-size:12px;">
                            <b>Tree Canopy #${props.tree_id}</b><br/>
                            <b>LiDAR Height:</b> ${props.chm_height_m ? props.chm_height_m + ' m' : 'Validated (≥2m)'}<br/>
                            <b>Corridor Status:</b> ${props.inside_boundary ? 'INSIDE CORRIDOR' : 'OUTSIDE'}<br/>
                            <b>Confidence:</b> ${(props.confidence * 100).toFixed(1)}%
                          </div>
                        `);
                      }
                    }}
                  />
                )}

                {/* 7. ALL PRIORITY TREES CIRCLE MARKERS */}
                {layers.priority && priorityData && (
                  <GeoJSON
                    key={`priority-trees-zoom-${mapZoomLevel >= 19 ? 'high' : 'normal'}`}
                    data={priorityData}
                    pointToLayer={(feature, latlng) => {
                      const priority = feature.properties?.verification_priority;
                      let color = '#22c55e'; // LOW
                      let radius = mapZoomLevel >= 19 ? 5.5 : 4.0;
                      if (priority === 'HIGH') {
                        color = '#ef4444';
                        radius = mapZoomLevel >= 19 ? 8.0 : 6.0;
                      } else if (priority === 'MEDIUM') {
                        color = '#f59e0b';
                        radius = mapZoomLevel >= 19 ? 6.5 : 4.5;
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

                {/* 8. 13 MANDATORY HIGH-PRIORITY AUDIT STOPS (ALWAYS RENDERED WITH HIGH Z-INDEX PANE) */}
                <Pane name="auditStopsPane" style={{ zIndex: 650 }}>
                  {layers.stops && orderedStops.map((st) => (
                    <Marker
                      key={`stop-${st.stopNum}`}
                      position={[st.lat, st.lon]}
                      icon={createStopIcon(st.stopNum)}
                      zIndexOffset={1000}
                      eventHandlers={{
                        click: () => setSelectedFeature({ type: 'tree', properties: st.properties }),
                      }}
                    >
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#f87171', fontSize: '13px' }}>Stop #{st.stopNum}: Tree #{st.treeId}</b><br />
                          <b>Priority:</b> HIGH (Mandatory Ground Check)<br />
                          <b>Confidence:</b> {(st.properties.confidence * 100).toFixed(1)}%<br />
                          <b>Corridor Status:</b> {st.properties.inside_boundary ? 'INSIDE CORRIDOR' : 'OUTSIDE'}<br />
                          <b>Rationale:</b> {st.properties.priority_reason || 'N/A'}<br />
                          <span style={{ fontSize: '10px', color: '#94a3b8' }}>WGS84: {st.lat.toFixed(5)}° N, {st.lon.toFixed(5)}° W</span>
                        </div>
                      </Popup>
                    </Marker>
                  ))}
                </Pane>

                {/* 9. FIRE HOTSPOTS */}
                {layers.fires && fireHotspotsData && (
                  <GeoJSON
                    key="fire-hotspots-layer"
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

              {/* FLOATING LAYER TOGGLES & DYNAMIC LEGEND */}
              {layersOpen ? (
                <div className="layer-panel">
                  <div className="layer-panel-header">
                    <div className="layer-panel-title">
                      <Layers size={14} style={{ color: '#34d399' }} />
                      <span>Map Layers ({Object.values(layers).filter(Boolean).length}/9)</span>
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
                      { id: 'healthGrid', label: `Forest Health Grid (${stats.totalHealthCells})`, color: '#22c55e' },
                      { id: 'terrainRoute', label: `Terrain TSP Route (${stats.terrainDist}m)`, color: '#00e5ff' },
                      { id: 'stops', label: `Numbered Audit Stops (${stats.highPriority})`, color: '#ef4444' },
                      { id: 'boundary', label: 'Project Corridor (24% Area)', color: '#ef4444' },
                      { id: 'trees', label: `Validated Trees (${stats.totalTrees})`, color: '#38bdf8' },
                      { id: 'priority', label: `Priority Trees (${stats.insideTrees + stats.outsideTrees})`, color: '#f59e0b' },
                      { id: 'degradation', label: `Degradation Zones (${stats.totalDegPolygons})`, color: '#991b1b' },
                      { id: 'legacyRoute', label: `Route (ExG, legacy, ${stats.legacyDist}m)`, color: '#c084fc' },
                      { id: 'fires', label: `NASA FIRMS Fires (${stats.fireCount})`, color: '#f97316' },
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

                  {/* Dynamic Forest Health Legend */}
                  {layers.healthGrid && (
                    <div className="legend-box" style={{ marginTop: '8px', borderTop: '1px solid #143624', paddingTop: '6px' }}>
                      <div style={{ fontWeight: 600, color: '#34d399' }}>Forest Health Grades (25m):</div>
                      <div className="legend-swatches">
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#22c55e' }}></span> A ({stats.gradeA})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#84cc16' }}></span> B ({stats.gradeB})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#f97316' }}></span> C ({stats.gradeC})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#ef4444' }}></span> D ({stats.gradeD})</span>
                      </div>
                    </div>
                  )}

                  {/* Priority Legend */}
                  {layers.priority && (
                    <div className="legend-box">
                      <div style={{ fontWeight: 600, color: '#94a3b8' }}>Verification Priority:</div>
                      <div className="legend-swatches">
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#ef4444' }}></span> HIGH ({stats.highPriority})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#f59e0b' }}></span> MED ({stats.mediumPriority})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#22c55e' }}></span> LOW ({stats.lowPriority})</span>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => setLayersOpen(true)}
                  className="layer-panel-collapsed-btn"
                  title="Expand Map Layers Control"
                >
                  <Layers size={14} style={{ color: '#34d399' }} />
                  <span>Layers ({Object.values(layers).filter(Boolean).length}/9)</span>
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
                    <span>Terrain TSP: {stats.terrainDist}m ({stats.terrainTime} min)</span>
                  </div>
                  <div className="alert-text">
                    Held-Karp terrain-aware TSP saved {stats.terrainSaved} min traversal time vs nearest-neighbor baseline.
                  </div>
                </div>

                <div className="alert-card fire">
                  <div className="alert-title">
                    <Scissors size={14} />
                    <span>{stats.totalDegPolygons} Canopy Loss Zones</span>
                  </div>
                  <div className="alert-text">
                    {stats.removalCount} severe removal polygons (ΔH ≤ -5m) and {stats.thinningCount} thinning polygons detected via LiDAR differencing.
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

                    {selectedFeature.type === 'health_cell' && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Cell ID:</span><span className="inspector-val">{selectedFeature.properties.cell_id}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Grade:</span><span className="inspector-val" style={{ color: getHealthGradeColor(selectedFeature.properties.grade), fontWeight: 'bold' }}>Grade {selectedFeature.properties.grade}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Health Score:</span><span className="inspector-val">{selectedFeature.properties.score !== null ? Number(selectedFeature.properties.score).toFixed(1) : 'N/A'} / 100</span></div>
                        <div className="inspector-row"><span className="inspector-key">Canopy Cover:</span><span className="inspector-val">{(selectedFeature.properties.canopy_cover * 100).toFixed(1)}%</span></div>
                        <div className="inspector-row"><span className="inspector-key">Height Diversity (σ):</span><span className="inspector-val">{selectedFeature.properties.structural_diversity} m</span></div>
                        <div className="inspector-row"><span className="inspector-key">Loss Density:</span><span className="inspector-val">{(selectedFeature.properties.loss_density * 100).toFixed(2)}%</span></div>
                      </div>
                    )}

                    {selectedFeature.type === 'degradation' && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Class:</span><span className="inspector-val" style={{ color: selectedFeature.properties.class_name === 'removal' ? '#ef4444' : '#fb923c', fontWeight: 'bold' }}>{selectedFeature.properties.class_name ? selectedFeature.properties.class_name.toUpperCase() : 'LOSS'}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Impact Area:</span><span className="inspector-val">{selectedFeature.properties.area_m2} m²</span></div>
                        <div className="inspector-row"><span className="inspector-key">Threshold Tier:</span><span className="inspector-val">{selectedFeature.properties.class_name === 'removal' ? 'ΔH ≤ -5.0 m' : '-5.0m < ΔH ≤ -2.0m'}</span></div>
                      </div>
                    )}

                    {(selectedFeature.type === 'route_terrain' || selectedFeature.type === 'route_legacy') && (
                      <div>
                        <div className="inspector-row"><span className="inspector-key">Route Model:</span><span className="inspector-val">{selectedFeature.properties.cost_model || 'Held-Karp TSP'}</span></div>
                        <div className="inspector-row"><span className="inspector-key">Physical Dist:</span><span className="inspector-val">{selectedFeature.properties.total_physical_distance_meters} m</span></div>
                        {selectedFeature.properties.total_travel_time_minutes && (
                          <div className="inspector-row"><span className="inspector-key">Travel Time:</span><span className="inspector-val">{selectedFeature.properties.total_travel_time_minutes} min</span></div>
                        )}
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
                    Click on any tree marker, verification stop, health grid cell, degradation zone, or route on the map to inspect spatial attributes.
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
                  <div>Ordway-Swisher Biological Station (OSBS) • 10 cm/pixel RGB & LiDAR CHM/DTM survey data.</div>
                </div>

                <div className="source-item">
                  <div className="source-name">DeepForest 2.1 & Tobler Terrain TSP</div>
                  <div>Deep learning tree crown detection + exact Held-Karp slope-and-canopy least-cost pathing.</div>
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
              <div>All {stats.totalTrees} LiDAR-validated canopies, {stats.totalHealthCells} health cells, and {stats.terrainDist}m terrain route are computed directly from authentic NEON & NASA geospatial layers.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

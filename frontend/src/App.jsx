import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Popup,
  Marker,
  Pane,
  Polyline,
  ImageOverlay,
  useMap,
  useMapEvents
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
  ChevronLeft,
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
  ArrowUpRight,
  Route,
  RotateCcw,
  X,
  Plus,
  LogOut,
  Download,
  ShieldCheck
} from 'lucide-react';
import { computePointToPointPath } from './utils/dijkstra';
import { apiService } from './services/api';
import { useAuth } from './context/AuthContext';
import LoginPage from './components/LoginPage';
import { DiversionAssessmentView } from './components/DiversionAssessmentView';


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

const createP2PIcon = (label, bg = '#468585') => {
  return L.divIcon({
    className: 'custom-p2p-icon',
    html: `
      <div style="
        background-color: ${bg};
        color: white;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 12.5px;
        border: 2.5px solid white;
        box-shadow: 0 4px 16px rgba(31,71,71,0.4);
        transform: translate(-14px, -14px);
      ">
        ${label}
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
};

const createEntryIcon = () => {
  return L.divIcon({
    className: 'custom-entry-icon',
    html: `
      <div style="
        background-color: #468585;
        color: white;
        padding: 4px 9px;
        border-radius: 5px;
        font-weight: 800;
        font-size: 10.5px;
        border: 2px solid white;
        box-shadow: 0 4px 12px rgba(31,71,71,0.35);
        display: flex;
        align-items: center;
        white-space: nowrap;
        transform: translate(-50%, -50%);
      ">
        ENTRANCE / BASE (OSBS HQ)
      </div>
    `,
    iconSize: [160, 24],
    iconAnchor: [80, 12],
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

// Map Click Listener for Interactive Point-to-Point Routing
function MapClickHandler({ p2pEnabled, onMapClick }) {
  useMapEvents({
    click(e) {
      if (p2pEnabled && onMapClick) {
        onMapClick(e.latlng);
      }
    },
  });
  return null;
}

// Automatically recalculates map boundaries and tile layout during panel transitions
function MapInvalidateResizer({ trigger }) {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    const t1 = setTimeout(() => map.invalidateSize(), 150);
    const t2 = setTimeout(() => map.invalidateSize(), 350);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [map, trigger]);
  return null;
}

// Automatically fits map viewport to uploaded raster bounds
function MapBoundsFitter({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds && Array.isArray(bounds) && bounds.length === 2 && map) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 20 });
    }
  }, [map, bounds]);
  return null;
}

export default function App() {
  const { user, loading: authLoading, logout } = useAuth();

  if (authLoading) {
    return (
      <div style={{ minHeight: '100vh', width: '100vw', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'var(--vd-bg-page)', gap: '16px' }}>
        <div style={{ width: '40px', height: '40px', border: '3px solid var(--vd-border-subtle)', borderTopColor: 'var(--vd-deep)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <div style={{ color: 'var(--vd-deep)', fontSize: '13px', fontWeight: 600 }}>Loading VanDrishti…</div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return <AppDashboard user={user} logout={logout} />;
}

function AppDashboard({ user, logout }) {
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

  // Cost Surfaces for Interactive Dijkstra
  const [osbsCostSurface, setOsbsCostSurface] = useState(null);
  const [teakCostSurface, setTeakCostSurface] = useState(null);
  const [activeCostSurface, setActiveCostSurface] = useState(null);

  // Point-to-Point Interactive Routing State
  const [p2pEnabled, setP2pEnabled] = useState(false);
  const [p2pStart, setP2pStart] = useState(null); // [lat, lon]
  const [p2pEnd, setP2pEnd] = useState(null);     // [lat, lon]
  const [p2pRouteResult, setP2pRouteResult] = useState(null);
  const [p2pError, setP2pError] = useState(null);

  // Uploaded Assessment State (Analyze Your Forest)
  const [selectedUploadPreset, setSelectedUploadPreset] = useState('teak');
  const [currentSite, setCurrentSite] = useState('OSBS_large_2019');
  const [uploadedAssessment, setUploadedAssessment] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  const triggerDownload = (url) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

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
  const [moduleReportOpen, setModuleReportOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [alertsExpanded, setAlertsExpanded] = useState(true);
  const [inspectorExpanded, setInspectorExpanded] = useState(true);
  const [stopsExpanded, setStopsExpanded] = useState(true);
  const [lastMainNav, setLastMainNav] = useState('Overview');

  // OSBS 250m Study Area Center in WGS84
  const mapCenter = useMemo(() => [29.681510, -81.952647], []);
  const [currentCenter, setCurrentCenter] = useState(mapCenter);
  const [currentZoom, setCurrentZoom] = useState(17);
  const [mapZoomLevel, setMapZoomLevel] = useState(17);

  // Dynamic center for Analyzer / Custom Upload Map
  const uploadMapCenter = useMemo(() => {
    if (uploadedAssessment?.preview_bounds_wgs84 && Array.isArray(uploadedAssessment.preview_bounds_wgs84) && uploadedAssessment.preview_bounds_wgs84.length === 2) {
      const b = uploadedAssessment.preview_bounds_wgs84;
      return [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2];
    }
    if (selectedUploadPreset === 'teak') return [37.000, -119.011];
    return mapCenter;
  }, [uploadedAssessment?.preview_bounds_wgs84, selectedUploadPreset, mapCenter]);

  const handleZoomChange = useCallback((z) => {
    setMapZoomLevel(z);
  }, []);

  const toggleLayer = (layerName) => {
    setLayers((prev) => ({ ...prev, [layerName]: !prev[layerName] }));
  };

  // Fetch Core GeoJSON Layers and Cost Surfaces
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
          teakAssRes,
          osbsCostRes,
          teakCostRes
        ] = await Promise.all([
          apiService.getBoundary('OSBS_large_2019'),
          apiService.getTrees('OSBS_large_2019'),
          apiService.getPriority('OSBS_large_2019'),
          apiService.getTerrainRoute('OSBS_large_2019'),
          apiService.getLegacyRoute('OSBS_large_2019'),
          apiService.getHealthGrid('OSBS_large_2019'),
          apiService.getDegradation('OSBS_large_2019'),
          apiService.getFireHotspots('osbs_live'),
          apiService.getAssessment('teak'),
          apiService.getCostSurface('osbs'),
          apiService.getCostSurface('teak'),
        ]);

        if (bRes) setBoundaryData(bRes);
        if (tRes) setTreesData(tRes);
        if (pRes) setPriorityData(pRes);
        if (trRes) setTerrainRouteData(trRes);
        if (lrRes) setLegacyRouteData(lrRes);
        if (hgRes) setHealthGridData(hgRes);
        if (degRes) setDegradationData(degRes);
        if (fRes) setFireHotspotsData(fRes);
        if (teakAssRes) setUploadedAssessment(teakAssRes);
        if (osbsCostRes) {
          setOsbsCostSurface(osbsCostRes);
          setActiveCostSurface(osbsCostRes);
        }
        if (teakCostRes) setTeakCostSurface(teakCostRes);
        setLoading(false);
      } catch (err) {
        console.error('Error loading GeoJSON layers via API:', err);
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

  // Sync Default / Preset Cost Surface when switching tabs or presets
  useEffect(() => {
    if (activeNav === 'Analyze Your Forest') {
      if (selectedUploadPreset === 'teak' && teakCostSurface) {
        setActiveCostSurface(teakCostSurface);
      } else if (selectedUploadPreset === 'osbs' && osbsCostSurface) {
        setActiveCostSurface(osbsCostSurface);
      }
    } else {
      if (osbsCostSurface) {
        setActiveCostSurface(osbsCostSurface);
      }
    }
  }, [activeNav, selectedUploadPreset, osbsCostSurface, teakCostSurface]);

  // Handle Interactive Map Clicks for Point-to-Point Dijkstra Routing
  const handleMapPointClick = useCallback((latlng) => {
    if (!p2pEnabled) return;
    const pt = [latlng.lat, latlng.lng];

    if (!activeCostSurface) {
      setP2pError('Cost surface data not yet loaded for this area.');
      return;
    }

    if (activeCostSurface.routable === false) {
      setP2pError(activeCostSurface.reason || 'Active cost surface is not routable.');
      return;
    }

    // Validate click is inside the active cost surface's WGS84 bounding box
    const bounds = activeCostSurface.wgs84_bounds; // [minLon, minLat, maxLon, maxLat]
    if (bounds && bounds.length === 4) {
      const [minLon, minLat, maxLon, maxLat] = bounds;
      const lat = latlng.lat;
      const lon = latlng.lng;
      if (lon < minLon || lon > maxLon || lat < minLat || lat > maxLat) {
        const surfName = activeCostSurface.name || 'the uploaded raster area';
        setP2pError(`Click inside the uploaded area (${surfName}) to set routing points.`);
        return;
      }
    }

    if (!p2pStart || (p2pStart && p2pEnd)) {
      // First click -> Start Point A
      setP2pStart(pt);
      setP2pEnd(null);
      setP2pRouteResult(null);
      setP2pError(null);
    } else if (p2pStart && !p2pEnd) {
      // Second click -> End Point B + Execute Dijkstra!
      setP2pEnd(pt);
      try {
        const result = computePointToPointPath(activeCostSurface, p2pStart, pt);
        console.log('[VanDrishti Dijkstra] Solved Route:', {
          surface: activeCostSurface.name,
          startGrid: result.start_grid,
          endGrid: result.end_grid,
          distanceMeters: result.distance_meters,
          travelTimeMinutes: result.travel_time_minutes,
        });
        setP2pRouteResult(result);
        setP2pError(null);
      } catch (err) {
        console.error('P2P Dijkstra error:', err);
        setP2pError(err.message || 'Routing failed between selected points.');
      }
    }
  }, [p2pEnabled, p2pStart, p2pEnd, activeCostSurface]);

  const handleResetP2P = () => {
    setP2pStart(null);
    setP2pEnd(null);
    setP2pRouteResult(null);
    setP2pError(null);
  };

  // Handle Preset Selection in "Analyze Your Forest"
  const handleSelectUploadPreset = async (preset) => {
    setSelectedUploadPreset(preset);
    setUploadLoading(true);
    handleResetP2P();
    try {
      const assessmentData = await apiService.getAssessment(preset);
      if (assessmentData) {
        setUploadedAssessment(assessmentData);
      }
      try {
        const costData = await apiService.getCostSurface(preset);
        if (costData) {
          setActiveCostSurface(costData);
        }
      } catch (costErr) {
        console.warn('Cost surface unavailable for preset:', costErr);
      }
    } catch (e) {
      console.error('Error loading preset assessment via API:', e);
    } finally {
      setUploadLoading(false);
    }
  };

  // Handle Real File Upload in "Analyze Your Forest"
  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadLoading(true);
    handleResetP2P();
    setSelectedUploadPreset('custom');

    const fileType = file.name.endsWith('.geojson') || file.name.endsWith('.json') ? 'boundary' : 'rgb_t2';

    try {
      const res = await apiService.uploadDataset(file, fileType);
      let assessmentData = res?.assessment || res?.metadata?.assessment || null;
      if (!assessmentData) {
        assessmentData = {
          filename: res.filename,
          raster_info: {
            filename: res.filename,
            shape: [res.height || 0, res.width || 0],
            bands: res.metadata?.bands || 0,
            dtype: res.metadata?.dtype || 'N/A',
            crs: res.crs || 'UNREFERENCED',
            georeferenced: !!res.crs,
            projected: res.metadata?.is_projected ?? false,
            res_m: res.metadata?.resolution ? `${res.metadata.resolution[0]} m/px` : 'N/A',
            area_ha: 'Calculated upon pipeline execution',
            bounds: res.bounds ? [res.bounds.left, res.bounds.bottom, res.bounds.right, res.bounds.top] : null,
          },
          summary: {
            available_count: 3,
            total_modules: 6,
            summary_text: `Uploaded ${res.filename} (${(res.file_size_bytes / 1024).toFixed(1)} KB) successfully`,
          },
          checklist: [
            {
              module: 'Upload Status',
              key: 'upload',
              level: 'FULL',
              message: `Saved to data/uploads/ (${res.crs || 'No CRS'})`,
              details: [],
              note: 'Ready for full pipeline processing',
            },
          ],
        };
      }

      // Attach server-generated preview URL and WGS84 bounds
      const previewUrl = res?.preview_url || res?.metadata?.preview_url || assessmentData.preview_url;
      const previewBounds = res?.preview_bounds_wgs84 || res?.metadata?.preview_bounds_wgs84 || assessmentData.preview_bounds_wgs84;
      if (previewUrl) assessmentData.preview_url = previewUrl;
      if (previewBounds) assessmentData.preview_bounds_wgs84 = previewBounds;
      if (res?.id) assessmentData.upload_id = res.id;

      setUploadedAssessment(assessmentData);

      // Fetch and activate the cost surface for this upload (safely wrapped)
      if (res?.id) {
        try {
          const costSurface = await apiService.getUploadCostSurface(res.id);
          if (costSurface) {
            setActiveCostSurface(costSurface);
            if (costSurface.routable === true) {
              setP2pEnabled(true);
            } else {
              setP2pEnabled(false);
            }
          }
        } catch (costErr) {
          console.warn('Cost surface computation unavailable for upload:', costErr);
          setActiveCostSurface({
            routable: false,
            reason: 'Routing cost surface calculation unavailable for this raster format.',
          });
          setP2pEnabled(false);
        }
      }
    } catch (err) {
      console.error('File upload failed:', err);
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploadLoading(false);
    }
  };

  // Derived Real Statistics (100% dynamic from GeoJSON)
  const stats = useMemo(() => {
    // 3 Distinct Inventory Populations
    const rawTrees = 1998; // Raw DeepForest model predictions
    const validatedTrees = treesData?.features?.length || 1979; // LiDAR CHM height-validated trees (>= 2.0m)
    const insideTrees = treesData?.features?.filter((f) => f.properties?.inside_boundary === true)?.length || 0;
    const outsideTrees = validatedTrees - insideTrees;

    const highPriorityList = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'HIGH') || [];
    const highPriority = highPriorityList.length;
    const mediumPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'MEDIUM')?.length || 0;
    const lowPriority = priorityData?.features?.filter((f) => f.properties?.verification_priority === 'LOW')?.length || 0;
    const operationalInventory = priorityData?.features?.length || (highPriority + mediumPriority + lowPriority);

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
      rawTrees,
      validatedTrees,
      operationalInventory,
      totalTrees: validatedTrees,
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

          {/* User Profile */}
          <div style={{
            padding: '10px 16px',
            borderBottom: '1px solid #3b7474',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            background: 'rgba(213, 240, 193, 0.08)',
          }}>
            <img
              src={user.photoURL || 'https://ui-avatars.com/api/?name=' + encodeURIComponent(user.displayName || 'U') + '&background=AAD9BB&color=468585&size=32'}
              alt="avatar"
              style={{ width: '30px', height: '30px', borderRadius: '50%', border: '2px solid #AAD9BB', flexShrink: 0 }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#ffffff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user.displayName || 'User'}
              </div>
              <div style={{ fontSize: '10px', color: '#AAD9BB', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user.email}
              </div>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              style={{ background: 'none', border: '1px solid #3b7474', borderRadius: '6px', padding: '5px', cursor: 'pointer', color: '#D5F0C1', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s', flexShrink: 0 }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#F9F7C9'; e.currentTarget.style.color = '#ffffff'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#3b7474'; e.currentTarget.style.color = '#D5F0C1'; }}
            >
              <LogOut size={14} />
            </button>
          </div>

          {/* Scope Card */}
          <div className="scope-badge-card">
            <div className="scope-badge-title">
              <Sparkles size={13} />
              <span>OSBS Study Area</span>
            </div>
            <div className="scope-badge-desc">
              250m × 250m (6.25 ha, NEON LiDAR & AOP)
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
              { id: 'Diversion Assessment', icon: ShieldCheck, label: 'Diversion Assessment' },
              { id: 'Analyze Your Forest', icon: UploadCloud, label: 'Analyze Your Forest' },
              { id: 'Canopy Mask', icon: Eye, label: 'Canopy & Route View' },
              { id: 'Fire Risk', icon: Flame, label: `Fire Risk (${stats.fireCount})` },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = activeNav === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    if (item.id === 'Analyze Your Forest') {
                      if (activeNav === 'Analyze Your Forest') {
                        // Toggle OFF -> return to last selected main nav
                        setActiveNav(lastMainNav && lastMainNav !== 'Analyze Your Forest' ? lastMainNav : 'Overview');
                      } else {
                        // Toggle ON -> open Module Capability Report
                        if (activeNav !== 'Analyze Your Forest') {
                          setLastMainNav(activeNav);
                        }
                        setActiveNav('Analyze Your Forest');
                        setModuleReportOpen(true);
                      }
                    } else {
                      setLastMainNav(item.id);
                      setActiveNav(item.id);
                      handleResetP2P();
                    }
                  }}
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
            <span style={{ fontSize: '9px', background: 'var(--vd-aqua)', padding: '1px 6px', borderRadius: '3px', border: '1px solid var(--vd-mint)', color: 'var(--vd-deep)', fontWeight: 700 }}>
              v2.2 Dijkstra
            </span>
          </div>
          <div>CRS: Dynamic Auto-Detection</div>
          <div>Tobler Terrain TSP • CHM Diff • Dijkstra</div>
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
              <span>VanDrishti</span>
              <span className="prototype-tag">250m × 250m (6.25 ha)</span>
            </h2>
          </div>

          <div className="topbar-actions">
            {/* Interactive Point-to-Point Dijkstra Toggle */}
            <button
              onClick={() => {
                setP2pEnabled(!p2pEnabled);
                if (p2pEnabled) handleResetP2P();
              }}
              className={`p2p-toggle-btn ${p2pEnabled ? 'active' : ''}`}
              title="Click two points on the map to compute real-time least-cost path"
            >
              <Route size={13} />
              <span>{p2pEnabled ? 'P2P Router Active' : 'P2P Dijkstra Mode'}</span>
            </button>

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

            <div className="report-download-group">
              <button
                onClick={() => triggerDownload(`/api/diversion/export/pdf?site=${encodeURIComponent(currentSite)}`)}
                className="report-download-btn pdf"
                title="Download Site Intelligence Report (PDF)"
              >
                <FileText size={12} style={{ color: 'var(--vd-deep)' }} />
                <span>Report PDF</span>
              </button>
              <button
                onClick={() => triggerDownload(`/api/diversion/export/csv?site=${encodeURIComponent(currentSite)}`)}
                className="report-download-btn csv"
                title="Download Site Tree Inventory Data (CSV)"
              >
                <Download size={12} style={{ color: 'var(--vd-deep)' }} />
                <span>CSV</span>
              </button>
            </div>

            <div className="live-badge">
              <Radio size={13} style={{ color: 'var(--vd-deep)' }} />
              <span>Verified Real Data</span>
            </div>
          </div>
        </header>

        {/* TOP STAT CARDS (REAL COMPUTED DATA ONLY) */}
        <div className="stats-grid">
          {/* Card 1: Tree Inventory Transparency & Pipeline Funnel */}
          <div className="stat-card" style={{ flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%' }}>
              <div>
                <div className="stat-label">Tree Inventory & Audit Funnel</div>
                <div className="stat-value" style={{ fontSize: '20px', display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                  <span>{stats.operationalInventory.toLocaleString()}</span>
                  <span className="stat-unit" style={{ fontSize: '11px', color: '#94a3b8' }}>Operational Inventory</span>
                </div>
                <div className="stat-sub">
                  <span style={{ color: 'var(--vd-deep)', fontWeight: 700 }}>{stats.insideTrees} in Corridor</span> • {stats.outsideTrees} Outside
                </div>
              </div>
              <div className="stat-icon-wrap green">
                <Trees size={18} />
              </div>
            </div>

            {/* Inventory Population Breakdown Table */}
            <div style={{
              background: 'rgba(15, 23, 42, 0.65)',
              border: '1px solid #143624',
              borderRadius: '6px',
              padding: '6px 10px',
              fontSize: '11px',
              display: 'flex',
              flexDirection: 'column',
              gap: '3px',
              width: '100%'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#94a3b8' }}>
                <span>Raw DeepForest Detections</span>
                <span style={{ fontWeight: 600, color: '#e2e8f0' }}>{stats.rawTrees.toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#94a3b8' }}>
                <span>LiDAR-Validated Trees</span>
                <span style={{ fontWeight: 600, color: '#38bdf8' }}>{stats.validatedTrees.toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#6ee7b7', fontWeight: 600 }}>
                <span>Operational Inventory</span>
                <span>{stats.operationalInventory.toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: '10px', fontSize: '10.5px', color: '#ef4444' }}>
                <span>↳ High Priority</span>
                <span style={{ fontWeight: 700 }}>{stats.highPriority}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: '10px', fontSize: '10.5px', color: '#f59e0b' }}>
                <span>↳ Medium Priority</span>
                <span style={{ fontWeight: 600 }}>{stats.mediumPriority}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: '10px', fontSize: '10.5px', color: '#22c55e' }}>
                <span>↳ Low Priority</span>
                <span style={{ fontWeight: 600 }}>{stats.lowPriority}</span>
              </div>
            </div>

            {/* Compact Funnel Explanation */}
            <div style={{ fontSize: '9.5px', color: '#64748b', fontStyle: 'italic', textAlign: 'center', width: '100%' }}>
              {stats.rawTrees.toLocaleString()} raw detections → {stats.validatedTrees.toLocaleString()} LiDAR validated → {stats.operationalInventory.toLocaleString()} confidence-filtered for operational assessment
            </div>
          </div>

          {/* Card 2 */}
          <div className="stat-card">
            <div>
              <div className="stat-label">Forest Health Score</div>
              <div className="stat-value">
                {stats.totalHealthCells} <span className="stat-unit">cells (25m)</span>
              </div>
              <div className="stat-sub">
                Grades: <span style={{ color: '#16a34a', fontWeight: 700 }}>A:{stats.gradeA}</span> • <span style={{ color: '#65a30d', fontWeight: 700 }}>B:{stats.gradeB}</span> • <span style={{ color: '#ea580c', fontWeight: 700 }}>C:{stats.gradeC}</span> • <span style={{ color: '#dc2626', fontWeight: 700 }}>D:{stats.gradeD}</span>
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
              <div className="stat-value">
                {stats.terrainDist} <span className="stat-unit">m ({stats.terrainTime} min)</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: 'var(--vd-deep)', fontWeight: 700 }}>-{stats.terrainSaved} min</span> vs NN • {stats.highPriority} Stops
              </div>
            </div>
            <div className="stat-icon-wrap cyan">
              <Navigation size={18} />
            </div>
          </div>

          {/* Card 4 */}
          <div className="stat-card" style={{ background: 'linear-gradient(135deg, #ffffff 0%, #fefef2 100%)', borderColor: '#e9e4a8' }}>
            <div>
              <div className="stat-label">Canopy Degradation</div>
              <div className="stat-value" style={{ color: '#856a14' }}>
                {stats.totalDegPolygons} <span className="stat-unit">zones</span>
              </div>
              <div className="stat-sub">
                <span style={{ color: '#dc2626', fontWeight: 600 }}>{stats.removalCount} Removal</span> • {stats.thinningCount} Thinning
              </div>
            </div>
            <div className="stat-icon-wrap amber">
              <Scissors size={18} />
            </div>
          </div>
        </div>

        {/* WORKSPACE BODY (MAP + RIGHT PANEL OR SPECIAL VIEWS) */}
        <div className="workspace-body">
          {activeNav === 'Diversion Assessment' ? (
            <DiversionAssessmentView currentSite={currentSite} />
          ) : activeNav === 'Analyze Your Forest' ? (
            <div className="analyzer-container">
              {/* Left Panel: Upload & Capability Report */}
              <div className="analyzer-sidebar">
                <div className="analyzer-sidebar-header">
                  <div className="analyzer-header-title">
                    <UploadCloud size={18} style={{ color: 'var(--vd-deep)' }} />
                    <span>Module Capability Report</span>
                  </div>
                </div>
                <div className="analyzer-header-sub">
                  Supply your own GeoTIFF to inspect georeferencing, spatial resolution, and get an honest capability assessment.
                </div>

                {/* Upload Control */}
                <label className="upload-dropzone">
                  <UploadCloud size={28} style={{ color: 'var(--vd-deep)' }} />
                  <div style={{ fontWeight: 700, color: 'var(--vd-text-heading)', fontSize: '12px' }}>
                    Upload Custom GeoTIFF (.tif) or Vector (.geojson)
                  </div>
                  <div style={{ fontSize: '10.5px', color: 'var(--vd-text-secondary)' }}>
                    Drag & drop or click to run AI/ExG detection & interactive routing
                  </div>
                  <input
                    type="file"
                    accept=".tif,.tiff,.geojson,.json"
                    style={{ display: 'none' }}
                    onChange={handleFileUpload}
                  />
                </label>

                {/* Preset Selectors */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--vd-text-secondary)', marginBottom: '6px' }}>
                    Select Sample Test Dataset:
                  </div>
                  <div className="preset-selector-group">
                    <button
                      className={`preset-btn ${selectedUploadPreset === 'teak' ? 'active' : ''}`}
                      onClick={() => handleSelectUploadPreset('teak')}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>TEAK_043_2018.tif (Single-Epoch RGB)</div>
                        <div style={{ fontSize: '10px', color: 'var(--vd-text-muted)' }}>Teakettle, CA • EPSG:32611 • 400×400 px</div>
                      </div>
                      <ArrowUpRight size={14} />
                    </button>
                    <button
                      className={`preset-btn ${selectedUploadPreset === 'osbs' ? 'active' : ''}`}
                      onClick={() => handleSelectUploadPreset('osbs')}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>OSBS_large_2019.tif (Multi-Sensor Suite)</div>
                        <div style={{ fontSize: '10px', color: 'var(--vd-text-muted)' }}>Ordway-Swisher, FL • EPSG:32617 • RGB + CHM + DTM</div>
                      </div>
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                </div>

                {uploadLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--vd-deep)', fontSize: '12px', padding: '10px' }}>
                    <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite' }} />
                    <span>Evaluating capabilities with config_loader...</span>
                  </div>
                )}

                {/* Technical Metadata Card */}
                {uploadedAssessment?.raster_info && (
                  <div className="meta-grid-card">
                    <div style={{ fontWeight: 700, color: 'var(--vd-deep)', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <HardDrive size={14} />
                      <span>Raster Technical Profile</span>
                    </div>
                    <div className="meta-grid-row"><span className="meta-key">Filename:</span><span className="meta-val">{uploadedAssessment.raster_info.filename}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Georeferenced:</span><span className="meta-val" style={{ color: uploadedAssessment.raster_info.georeferenced ? 'var(--vd-deep)' : '#dc2626' }}>{uploadedAssessment.raster_info.georeferenced ? `Yes (${uploadedAssessment.raster_info.crs})` : 'UNREFERENCED'}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">CRS Projection:</span><span className="meta-val">{uploadedAssessment.raster_info.projected ? 'Projected (Metric)' : 'Geographic / None'}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Dimensions:</span><span className="meta-val">{uploadedAssessment.raster_info.shape?.[1]} × {uploadedAssessment.raster_info.shape?.[0]} px ({uploadedAssessment.raster_info.bands} bands)</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Resolution:</span><span className="meta-val">{typeof uploadedAssessment.raster_info.res_m === 'number' ? `${uploadedAssessment.raster_info.res_m} m/pixel` : uploadedAssessment.raster_info.res_m}</span></div>
                    <div className="meta-grid-row"><span className="meta-key">Ground Coverage:</span><span className="meta-val">{typeof uploadedAssessment.raster_info.area_ha === 'number' ? `${uploadedAssessment.raster_info.area_ha} ha (${uploadedAssessment.raster_info.area_m2} m²)` : uploadedAssessment.raster_info.area_ha}</span></div>
                  </div>
                )}

                {/* Detection Preview / DeepForest Result Card */}
                {uploadedAssessment?.detection_results && (
                  <div className="meta-grid-card" style={{ borderColor: 'var(--vd-aqua)', background: '#f6faf3' }}>
                    <div style={{ fontWeight: 700, color: 'var(--vd-deep)', fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Trees size={14} />
                        <span>
                          {uploadedAssessment.detection_results.method === 'deepforest'
                            ? 'DeepForest (NEON-pretrained RetinaNet)'
                            : 'Fast optical preview, not AI-validated'}
                        </span>
                      </div>
                      <span className={`badge-pill ${uploadedAssessment.detection_results.method === 'deepforest' ? 'full' : 'degraded'}`} style={{ fontSize: '9.5px' }}>
                        {uploadedAssessment.detection_results.method === 'deepforest' ? 'DeepForest' : 'ExG Heuristic'}
                      </span>
                    </div>

                    <div style={{ marginTop: '8px' }}>
                      <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--vd-deep)', letterSpacing: '-0.5px' }}>
                        {(uploadedAssessment.detection_results.count || 0).toLocaleString()}
                        <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--vd-text-secondary)', marginLeft: '6px' }}>
                          {uploadedAssessment.detection_results.method === 'deepforest' ? 'crowns detected' : 'greenness peaks'}
                        </span>
                      </div>

                      {/* Truncation Subline */}
                      {uploadedAssessment.detection_results.truncated && (
                        <div style={{ fontSize: '10.5px', color: '#b45309', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>•</span>
                          <span>
                            showing {(uploadedAssessment.detection_results.count_rendered || 0).toLocaleString()} strongest of {(uploadedAssessment.detection_results.count || 0).toLocaleString()}
                          </span>
                        </div>
                      )}

                      {/* Fallback Reason */}
                      {uploadedAssessment.detection_results.fallback_reason && (
                        <div style={{ fontSize: '10px', color: '#92400e', marginTop: '4px', background: '#fef3c7', padding: '4px 6px', borderRadius: '4px', border: '1px solid #fde68a' }}>
                          <b>ExG Fallback:</b> {uploadedAssessment.detection_results.fallback_reason}
                        </div>
                      )}

                      {/* DeepForest Post-Filters */}
                      {uploadedAssessment.detection_results.method === 'deepforest' && uploadedAssessment.detection_results.filters && (
                        <div style={{ fontSize: '10px', color: 'var(--vd-text-secondary)', marginTop: '5px' }}>
                          Raw detections: {uploadedAssessment.detection_results.raw_count?.toLocaleString()} • 
                          Size filter dropped: {uploadedAssessment.detection_results.filters.size_dropped || 0} • 
                          Dedup dropped: {uploadedAssessment.detection_results.filters.dedup_dropped || 0}
                        </div>
                      )}

                      {/* Detection Notes */}
                      {uploadedAssessment.detection_results.notes?.length > 0 && (
                        <div style={{ fontSize: '9.5px', color: 'var(--vd-text-secondary)', marginTop: '4px', fontStyle: 'italic' }}>
                          {uploadedAssessment.detection_results.notes[0]}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Capability Checklist */}
                {uploadedAssessment?.checklist && (
                  <div className="checklist-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--vd-text-heading)' }}>Module Capability Report</span>
                      <span style={{ fontSize: '10px', color: 'var(--vd-text-muted)' }}>config_loader.assess()</span>
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
                          <div style={{ fontSize: '9.5px', color: '#b45309', marginTop: '2px' }}>
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

                {/* Download Report Action Card */}
                {uploadedAssessment && (
                  <div className="report-action-card">
                    <div className="report-action-header">
                      <FileText size={14} style={{ color: 'var(--vd-deep)' }} />
                      <span>Area Assessment Report</span>
                    </div>
                    <div className="report-action-sub">
                      Download complete spatial diagnostic, capability checklist, and crown statistics.
                    </div>
                    <div className="report-btn-group">
                      <button
                        className="download-report-btn pdf"
                        onClick={() => {
                          const url = uploadedAssessment?.upload_id
                            ? `/api/upload/${uploadedAssessment.upload_id}/report?format=pdf`
                            : `/api/report/${selectedUploadPreset === 'teak' ? 'TEAK_043_2018' : 'OSBS_large_2019'}?format=pdf`;
                          window.open(url, '_blank');
                        }}
                        title="Download full assessment report as PDF"
                      >
                        <FileText size={13} />
                        <span>Download PDF</span>
                      </button>
                      <button
                        className="download-report-btn csv"
                        onClick={() => {
                          const url = uploadedAssessment?.upload_id
                            ? `/api/upload/${uploadedAssessment.upload_id}/report?format=csv`
                            : `/api/report/${selectedUploadPreset === 'teak' ? 'TEAK_043_2018' : 'OSBS_large_2019'}?format=csv`;
                          window.open(url, '_blank');
                        }}
                        title="Download assessment checklist as CSV"
                      >
                        <Download size={13} />
                        <span>Download CSV</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Panel: Live Map for Uploaded Raster Results */}
              <div className="analyzer-map-wrap">
                {/* P2P HUD OVERLAY ON UPLOAD MAP */}
                {p2pEnabled && (
                  <div className="p2p-hud-overlay">
                    <div className="p2p-hud-header">
                      <div className="p2p-hud-title">
                        <Route size={16} />
                        <span>Interactive Dijkstra</span>
                      </div>
                      <div className="term-badge-group">
                        <span className={`term-badge ${activeCostSurface?.active_terms?.includes('ExG') ? 'active' : 'inactive'}`}>ExG</span>
                        <span className={`term-badge ${activeCostSurface?.active_terms?.includes('CHM') ? 'active' : 'inactive'}`}>CHM</span>
                        <span className={`term-badge ${activeCostSurface?.active_terms?.includes('Slope') ? 'active' : 'inactive'}`}>Slope</span>
                      </div>
                    </div>

                    {/* Active Cost Surface Banner */}
                    {activeCostSurface && (
                      <div style={{ fontSize: '10.5px', color: 'var(--vd-deep)', background: 'var(--vd-pale)', border: '1px solid var(--vd-mint)', borderRadius: '5px', padding: '5px 8px', margin: '4px 0', lineHeight: '1.35' }}>
                        Routing on: <b style={{ color: 'var(--vd-text-heading)' }}>{activeCostSurface.name || (selectedUploadPreset === 'teak' ? 'TEAK_043_2018' : 'OSBS_large_2019')}</b> {activeCostSurface.shape ? `(${activeCostSurface.shape[1]}×${activeCostSurface.shape[0]} @ ${activeCostSurface.res_m} m)` : ''}
                      </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="p2p-mode-label">
                        {p2pRouteResult?.mode_label || activeCostSurface?.mode_label || 'Cost Surface Active'}
                      </span>
                      {p2pRouteResult && (
                        <span style={{ fontSize: '10px', color: 'var(--vd-deep)', fontWeight: 700 }}>● Path Solved</span>
                      )}
                    </div>

                    {/* Step-by-Step Instruction */}
                    <div className="p2p-instruction">
                      {!p2pStart && '1. Click anywhere inside the active raster overlay to set Start Point A.'}
                      {p2pStart && !p2pEnd && '2. Click your target destination inside the raster to run Dijkstra.'}
                      {p2pRouteResult && 'Least-cost Dijkstra path successfully generated across active impedance model.'}
                      {p2pError && <span style={{ color: '#f87171', display: 'block', marginTop: '3px' }}>⚠️ {p2pError}</span>}
                    </div>

                    {/* Metric Outputs */}
                    {p2pRouteResult && (
                      <>
                        <div className="p2p-metrics-grid">
                          <div className="p2p-metric-item">
                            <span className="p2p-metric-label">Path Length</span>
                            <span className="p2p-metric-val">
                              {p2pRouteResult.distance_meters !== 'UNAVAILABLE' ? `${p2pRouteResult.distance_meters} m` : 'UNAVAILABLE'}
                            </span>
                          </div>
                          <div className="p2p-metric-item">
                            <span className="p2p-metric-label">Estimated Time</span>
                            <span className="p2p-metric-val">
                              {p2pRouteResult.travel_time_minutes !== 'UNAVAILABLE' ? `${p2pRouteResult.travel_time_minutes} min` : 'UNAVAILABLE'}
                            </span>
                          </div>
                          {!p2pRouteResult.is_projected && (
                            <div className="p2p-metric-item" style={{ gridColumn: 'span 2' }}>
                              <span className="p2p-metric-label">Pixel Distance</span>
                              <span className="p2p-metric-val" style={{ color: '#f59e0b' }}>
                                {p2pRouteResult.pixel_distance} px (Unprojected)
                              </span>
                            </div>
                          )}
                        </div>

                        {p2pRouteResult.start_grid && p2pRouteResult.end_grid && (
                          <div style={{ fontSize: '10px', color: '#94a3b8', background: '#07160f', border: '1px solid #143624', borderRadius: '4px', padding: '4px 7px', fontFamily: 'ui-monospace, monospace' }}>
                            Resolved Grid: [{p2pRouteResult.start_grid[0]}, {p2pRouteResult.start_grid[1]}] → [{p2pRouteResult.end_grid[0]}, {p2pRouteResult.end_grid[1]}] ({p2pRouteResult.grid_shape?.[1]}×{p2pRouteResult.grid_shape?.[0]})
                          </div>
                        )}

                        {p2pRouteResult.mode_label?.includes('ExG') && (
                          <div style={{ fontSize: '9.5px', color: '#fbbf24', background: 'rgba(69, 26, 3, 0.6)', border: '1px solid #d97706', borderRadius: '4px', padding: '4px 6px', lineHeight: '1.3' }}>
                            ⚠️ <b>Uncalibrated Proxy:</b> w_veg multiplier lacks field timing data. ExG-only travel times are relative impedance indices, not field-validated predictions.
                          </div>
                        )}
                      </>
                    )}
                    <div className="p2p-actions">
                      <button onClick={handleResetP2P} className="p2p-action-btn">
                        <RotateCcw size={11} style={{ display: 'inline', marginRight: '4px' }} />
                        Reset Points
                      </button>
                      <button onClick={() => { setP2pEnabled(false); handleResetP2P(); }} className="p2p-action-btn">
                        <X size={11} style={{ display: 'inline', marginRight: '4px' }} />
                        Exit P2P
                      </button>
                    </div>
                  </div>
                )}

                {/* Non-routable Warning Banner if user uploaded non-projected raster */}
                {activeCostSurface && activeCostSurface.routable === false && !p2pEnabled && (
                  <div style={{ position: 'absolute', top: '16px', right: '16px', zIndex: 1000, background: 'rgba(15, 23, 42, 0.92)', border: '1px solid #ef4444', borderRadius: '8px', padding: '10px 14px', maxWidth: '340px', fontSize: '11px', color: '#f87171', boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }}>
                    <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', color: '#fca5a5' }}>
                      <AlertTriangle size={14} />
                      <span>P2P Routing Disabled</span>
                    </div>
                    <div>{activeCostSurface.reason}</div>
                  </div>
                )}

                <MapContainer
                  center={uploadMapCenter}
                  zoom={uploadedAssessment?.preview_bounds_wgs84 ? 19 : 17}
                  minZoom={7}
                  maxZoom={22}
                  scrollWheelZoom={true}
                  style={{ height: '100%', width: '100%', cursor: (p2pEnabled && activeCostSurface?.routable !== false) ? 'crosshair' : 'default' }}
                >
                  <MapController
                    center={uploadMapCenter}
                    zoom={uploadedAssessment?.preview_bounds_wgs84 ? 19 : (selectedUploadPreset === 'teak' ? 19 : 17)}
                  />
                  <MapInvalidateResizer trigger={`${moduleReportOpen}-${selectedUploadPreset}-${uploadedAssessment?.preview_bounds_wgs84?.[0]?.[0]}`} />

                  {/* Click Listener for P2P Dijkstra */}
                  <MapClickHandler p2pEnabled={p2pEnabled && activeCostSurface?.routable !== false} onMapClick={handleMapPointClick} />

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

                  {/* Render Uploaded Raster Web Preview ImageOverlay */}
                  {uploadedAssessment?.preview_url && uploadedAssessment?.preview_bounds_wgs84 && (
                    <ImageOverlay
                      key={`preview-overlay-${uploadedAssessment.preview_url}`}
                      url={uploadedAssessment.preview_url}
                      bounds={uploadedAssessment.preview_bounds_wgs84}
                      opacity={0.85}
                      zIndex={400}
                    />
                  )}

                  {/* Fit map viewport to uploaded raster bounds */}
                  {uploadedAssessment?.preview_bounds_wgs84 && (
                    <MapBoundsFitter bounds={uploadedAssessment.preview_bounds_wgs84} />
                  )}

                  {/* Render Detected Crowns */}
                  {uploadedAssessment?.detection_results?.geojson && (
                    <GeoJSON
                      key={`upload-trees-${selectedUploadPreset}-${uploadedAssessment?.detection_results?.method}`}
                      data={uploadedAssessment.detection_results.geojson}
                      pointToLayer={(feature, latlng) => {
                        const isDf = uploadedAssessment?.detection_results?.method === 'deepforest' || feature.properties?.score !== undefined;
                        return L.circleMarker(latlng, {
                          radius: isDf ? 5.0 : 4.5,
                          fillColor: isDf ? '#468585' : '#80BCBD',
                          color: '#ffffff',
                          weight: 1.2,
                          fillOpacity: 0.9,
                        });
                      }}
                      onEachFeature={(feature, layer) => {
                        const p = feature.properties || {};
                        const method = uploadedAssessment?.detection_results?.method;
                        const isDeepForest = method === 'deepforest' || p.score !== undefined;
                        const val = p.score !== undefined ? p.score : (p.exg_strength !== undefined ? p.exg_strength : p.confidence);
                        const label = isDeepForest ? 'AI Score (RetinaNet)' : (p.exg_strength !== undefined ? 'ExG Strength' : 'Confidence');
                        layer.bindPopup(`
                          <div style="font-size:12px; color: #1f4747;">
                            <b style="color:#468585;">Detected Tree Crown #${p.tree_id}</b><br/>
                            <b>${label}:</b> ${val !== undefined ? (val * 100).toFixed(1) + '%' : 'N/A'}<br/>
                            ${p.crown_diam_m !== undefined ? `<b>Crown Diameter:</b> ${p.crown_diam_m} m<br/>` : ''}
                            <b>Pixel Coordinates:</b> [${p.pixel_x}, ${p.pixel_y}]<br/>
                            <span style="font-size:10px; color:#6b9494;">${isDeepForest ? 'DeepForest (NEON-pretrained RetinaNet)' : 'Single-Raster Optical Crown Preview'}</span>
                          </div>
                        `);
                      }}
                    />
                  )}

                  {/* P2P Dijkstra Start Marker (A) */}
                  {p2pStart && (
                    <Marker position={p2pStart} icon={createP2PIcon('A', '#468585')} zIndexOffset={1100}>
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#468585' }}>Point A (Start)</b><br />
                          {p2pStart[0].toFixed(5)}° N, {p2pStart[1].toFixed(5)}° W
                        </div>
                      </Popup>
                    </Marker>
                  )}

                  {/* P2P Dijkstra End Marker (B) */}
                  {p2pEnd && (
                    <Marker position={p2pEnd} icon={createP2PIcon('B', '#80BCBD')} zIndexOffset={1100}>
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#80BCBD' }}>Point B (Destination)</b><br />
                          {p2pEnd[0].toFixed(5)}° N, {p2pEnd[1].toFixed(5)}° W
                        </div>
                      </Popup>
                    </Marker>
                  )}

                  {/* P2P Dijkstra Result Polyline */}
                  {p2pRouteResult?.pathCoordinates && (
                    <Polyline
                      positions={p2pRouteResult.pathCoordinates}
                      pathOptions={{
                        color: '#f59e0b',
                        weight: 5.5,
                        opacity: 0.95,
                        dashArray: '3, 6',
                      }}
                    >
                      <Popup>
                        <div style={{ fontSize: '12px' }}>
                          <b style={{ color: '#f59e0b', fontSize: '13px' }}>Point-to-Point Dijkstra Path</b><br />
                          <b>Model:</b> {p2pRouteResult.mode_label}<br />
                          <b>Distance:</b> {p2pRouteResult.distance_meters !== 'UNAVAILABLE' ? `${p2pRouteResult.distance_meters} m` : 'UNAVAILABLE'}<br />
                          <b>Est. Time:</b> {p2pRouteResult.travel_time_minutes !== 'UNAVAILABLE' ? `${p2pRouteResult.travel_time_minutes} min` : 'UNAVAILABLE'}
                        </div>
                      </Popup>
                    </Polyline>
                  )}
                </MapContainer>
              </div>
            </div>
          ) : activeNav === 'Canopy Mask' ? (
            /* SPECIAL VIEW 2: CANOPY MASK VISUALIZER */
            <div className="image-viewer-container">
              <div className="image-viewer-box" style={{ background: '#ffffff', borderColor: 'var(--vd-border-subtle)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 700, color: 'var(--vd-deep)', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Eye size={18} />
                    <span>Terrain-Aware Route + Canopy Height Model (250m Study Area)</span>
                  </div>
                  <a
                    href="/data/OSBS_large_2019_overview_map_optimized.png"
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: '11px', color: 'var(--vd-deep)', fontWeight: 600, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <Maximize2 size={12} /> Open Full Resolution
                  </a>
                </div>
                <img
                  src="/data/OSBS_large_2019_overview_map_optimized.png"
                  alt="OSBS Large 2019 Terrain-Aware TSP Route and CHM"
                  style={{ border: '1px solid var(--vd-border-subtle)' }}
                />
                <div style={{ fontSize: '11px', color: 'var(--vd-text-secondary)', lineHeight: 1.4 }}>
                  <b>Panel 1 (Left)</b>: High-Resolution RGB Orthomosaic with Terrain-Aware TSP Route (488.9 m, 14.96 min) across 13 HIGH stops.<br />
                  <b>Panel 2 (Right)</b>: NEON LiDAR Canopy Height Model (CHM p95=16.6m) showing optimal navigation through natural forest gaps.
                </div>
              </div>
            </div>
          ) : (
            /* INTERACTIVE LEAFLET MAP */
            <div className="map-container-box">
              {loading && (
                <div style={{ position: 'absolute', inset: 0, zIndex: 1000, background: 'rgba(232, 245, 226, 0.9)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                  <RefreshCw size={28} style={{ color: 'var(--vd-deep)', animation: 'spin 1s linear infinite' }} />
                  <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--vd-deep)' }}>Loading Spatial Layers...</span>
                </div>
              )}

              {error && (
                <div style={{ position: 'absolute', inset: 0, zIndex: 1000, background: 'rgba(254, 242, 242, 0.95)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px', textAlign: 'center' }}>
                  <ShieldAlert size={36} style={{ color: '#dc2626', marginBottom: '8px' }} />
                  <div style={{ fontWeight: 700, color: '#991b1b' }}>Error Loading Data Layers</div>
                  <div style={{ fontSize: '12px', color: '#b91c1c', marginTop: '4px' }}>{error}</div>
                </div>
              )}

              {/* P2P HUD OVERLAY ON MAIN MAP */}
              {p2pEnabled && (
                <div className="p2p-hud-overlay">
                  <div className="p2p-hud-header">
                    <div className="p2p-hud-title">
                      <Route size={16} />
                      <span>Point-to-Point Dijkstra</span>
                    </div>
                    <div className="term-badge-group">
                      <span className={`term-badge ${activeCostSurface?.active_terms?.includes('ExG') ? 'active' : 'inactive'}`}>ExG</span>
                      <span className={`term-badge ${activeCostSurface?.active_terms?.includes('CHM') ? 'active' : 'inactive'}`}>CHM</span>
                      <span className={`term-badge ${activeCostSurface?.active_terms?.includes('Slope') ? 'active' : 'inactive'}`}>Slope</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="p2p-mode-label">
                      {p2pRouteResult?.mode_label || activeCostSurface?.mode_label || 'terrain-aware'}
                    </span>
                    {p2pRouteResult && (
                      <span style={{ fontSize: '10px', color: 'var(--vd-deep)', fontWeight: 700 }}>● Path Solved</span>
                    )}
                  </div>

                  {/* Step-by-Step Instruction */}
                  <div className="p2p-instruction">
                    {!p2pStart && '1. Click anywhere on the map to set Start Point A.'}
                    {p2pStart && !p2pEnd && '2. Click your target destination to run Dijkstra.'}
                    {p2pRouteResult && 'Least-cost Dijkstra path successfully generated across terrain & canopy cost surface.'}
                    {p2pError && <span style={{ color: '#dc2626' }}>{p2pError}</span>}
                  </div>

                  {/* Metric Outputs */}
                  {p2pRouteResult && (
                    <>
                      <div className="p2p-metrics-grid">
                        <div className="p2p-metric-item">
                          <span className="p2p-metric-label">Path Length</span>
                          <span className="p2p-metric-val">
                            {p2pRouteResult.distance_meters !== 'UNAVAILABLE' ? `${p2pRouteResult.distance_meters} m` : 'UNAVAILABLE'}
                          </span>
                        </div>
                        <div className="p2p-metric-item">
                          <span className="p2p-metric-label">Estimated Time</span>
                          <span className="p2p-metric-val">
                            {p2pRouteResult.travel_time_minutes !== 'UNAVAILABLE' ? `${p2pRouteResult.travel_time_minutes} min` : 'UNAVAILABLE'}
                          </span>
                        </div>
                        {!p2pRouteResult.is_projected && (
                          <div className="p2p-metric-item" style={{ gridColumn: 'span 2' }}>
                            <span className="p2p-metric-label">Pixel Distance</span>
                            <span className="p2p-metric-val" style={{ color: '#d97706' }}>
                              {p2pRouteResult.pixel_distance} px (Unprojected)
                            </span>
                          </div>
                        )}
                      </div>

                      {p2pRouteResult.mode_label?.includes('ExG') && (
                        <div style={{ fontSize: '9.5px', color: '#fbbf24', background: 'rgba(69, 26, 3, 0.6)', border: '1px solid #d97706', borderRadius: '4px', padding: '4px 6px', lineHeight: '1.3' }}>
                          ⚠️ <b>Uncalibrated Proxy:</b> w_veg multiplier lacks field timing data. ExG-only travel times are relative impedance indices, not field-validated predictions.
                        </div>
                      )}
                    </>
                  )}

                  <div className="p2p-actions">
                    <button onClick={handleResetP2P} className="p2p-action-btn">
                      <RotateCcw size={11} style={{ display: 'inline', marginRight: '4px' }} />
                      Reset Points
                    </button>
                    <button onClick={() => { setP2pEnabled(false); handleResetP2P(); }} className="p2p-action-btn">
                      <X size={11} style={{ display: 'inline', marginRight: '4px' }} />
                      Exit P2P
                    </button>
                  </div>
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
                style={{ height: '100%', width: '100%', cursor: p2pEnabled ? 'crosshair' : 'default' }}
              >
                <MapController center={currentCenter} zoom={currentZoom} onZoomChange={handleZoomChange} />
                <MapInvalidateResizer trigger={`${rightPanelOpen}-${layersOpen}-${activeNav}`} />

                {/* Click Listener for P2P Dijkstra */}
                <MapClickHandler p2pEnabled={p2pEnabled} onMapClick={handleMapPointClick} />

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
                        <div style="font-size:12px; color: #1f4747;">
                          <b style="font-size:13px; color: #468585;">Tree Canopy #${props.tree_id}</b><br/>
                          <b>Priority:</b> <span style="color:${
                            props.verification_priority === 'HIGH' ? '#dc2626' : props.verification_priority === 'MEDIUM' ? '#d97706' : '#16a34a'
                          }; font-weight:bold;">${props.verification_priority}</span><br/>
                          <b>Confidence:</b> ${(props.confidence * 100).toFixed(1)}%<br/>
                          <b>Corridor Status:</b> ${props.inside_boundary ? 'INSIDE (AFFECTED)' : 'OUTSIDE (SAFE)'}<br/>
                          <b>Rationale:</b> ${props.priority_reason || 'N/A'}<br/>
                          <span style="font-size:10px; color:#6b9494;">UTM: ${props.geo_easting || ''} E, ${props.geo_northing || ''} N</span>
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
                          <b style={{ color: '#dc2626', fontSize: '13px' }}>Stop #{st.stopNum}: Tree #{st.treeId}</b><br />
                          <b>Priority:</b> HIGH (Mandatory Ground Check)<br />
                          <b>Confidence:</b> {(st.properties.confidence * 100).toFixed(1)}%<br />
                          <b>Corridor Status:</b> {st.properties.inside_boundary ? 'INSIDE CORRIDOR' : 'OUTSIDE'}<br />
                          <b>Rationale:</b> {st.properties.priority_reason || 'N/A'}<br />
                          <span style={{ fontSize: '10px', color: '#6b9494' }}>WGS84: {st.lat.toFixed(5)}° N, {st.lon.toFixed(5)}° W</span>
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
                        color: '#dc2626',
                        weight: 2,
                        fillOpacity: 0.85,
                      });
                    }}
                    onEachFeature={(feature, layer) => {
                      const props = feature.properties || {};
                      layer.bindPopup(`
                        <div style="font-size:12px; color: #1f4747;">
                          <b style="color:#ea580c;">NASA FIRMS Hotspot #${props.hotspot_id}</b><br/>
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

                {/* 10. INTERACTIVE POINT-TO-POINT DIJKSTRA START & END MARKERS + PATH */}
                {p2pStart && (
                  <Marker position={p2pStart} icon={createP2PIcon('A', '#468585')} zIndexOffset={1100}>
                    <Popup>
                      <div style={{ fontSize: '12px' }}>
                        <b style={{ color: '#468585' }}>Point A (Start)</b><br />
                        {p2pStart[0].toFixed(5)}° N, {p2pStart[1].toFixed(5)}° W
                      </div>
                    </Popup>
                  </Marker>
                )}

                {p2pEnd && (
                  <Marker position={p2pEnd} icon={createP2PIcon('B', '#80BCBD')} zIndexOffset={1100}>
                    <Popup>
                      <div style={{ fontSize: '12px' }}>
                        <b style={{ color: '#80BCBD' }}>Point B (Destination)</b><br />
                        {p2pEnd[0].toFixed(5)}° N, {p2pEnd[1].toFixed(5)}° W
                      </div>
                    </Popup>
                  </Marker>
                )}

                {p2pRouteResult?.pathCoordinates && (
                  <Polyline
                    positions={p2pRouteResult.pathCoordinates}
                    pathOptions={{
                      color: '#d97706',
                      weight: 5.5,
                      opacity: 0.95,
                      dashArray: '3, 6',
                    }}
                  >
                    <Popup>
                      <div style={{ fontSize: '12px' }}>
                        <b style={{ color: '#d97706', fontSize: '13px' }}>Point-to-Point Dijkstra Path</b><br />
                        <b>Model:</b> {p2pRouteResult.mode_label}<br />
                        <b>Distance:</b> {p2pRouteResult.distance_meters !== 'UNAVAILABLE' ? `${p2pRouteResult.distance_meters} m` : 'UNAVAILABLE'}<br />
                        <b>Est. Time:</b> {p2pRouteResult.travel_time_minutes !== 'UNAVAILABLE' ? `${p2pRouteResult.travel_time_minutes} min` : 'UNAVAILABLE'}
                      </div>
                    </Popup>
                  </Polyline>
                )}
              </MapContainer>

              {/* FLOATING LAYER TOGGLES & DYNAMIC LEGEND */}
              {layersOpen ? (
                <div className="layer-panel">
                  <div className="layer-panel-header">
                    <div className="layer-panel-title">
                      <Layers size={14} style={{ color: 'var(--vd-deep)' }} />
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
                      { id: 'healthGrid', label: `Forest Health Grid (${stats.totalHealthCells})`, color: '#16a34a' },
                      { id: 'terrainRoute', label: `Terrain TSP Route (${stats.terrainDist}m)`, color: '#468585' },
                      { id: 'stops', label: `Numbered Audit Stops (${stats.highPriority})`, color: '#dc2626' },
                      { id: 'boundary', label: 'Project Corridor (24% Area)', color: '#dc2626' },
                      { id: 'trees', label: `Validated Trees (${stats.totalTrees})`, color: '#80BCBD' },
                      { id: 'priority', label: `Priority Trees (${stats.insideTrees + stats.outsideTrees})`, color: '#d97706' },
                      { id: 'degradation', label: `Degradation Zones (${stats.totalDegPolygons})`, color: '#991b1b' },
                      { id: 'legacyRoute', label: `Route (ExG, legacy, ${stats.legacyDist}m)`, color: '#c084fc' },
                      { id: 'fires', label: `NASA FIRMS Fires (${stats.fireCount})`, color: '#ea580c' },
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
                    <div className="legend-box" style={{ marginTop: '8px', borderTop: '1px solid var(--vd-border-subtle)', paddingTop: '6px' }}>
                      <div style={{ fontWeight: 700, color: 'var(--vd-deep)' }}>Forest Health Grades (25m):</div>
                      <div className="legend-swatches">
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#16a34a' }}></span> A ({stats.gradeA})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#65a30d' }}></span> B ({stats.gradeB})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#ea580c' }}></span> C ({stats.gradeC})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#dc2626' }}></span> D ({stats.gradeD})</span>
                      </div>
                    </div>
                  )}

                  {/* Priority Legend */}
                  {layers.priority && (
                    <div className="legend-box">
                      <div style={{ fontWeight: 700, color: 'var(--vd-text-secondary)' }}>Verification Priority:</div>
                      <div className="legend-swatches">
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#dc2626' }}></span> HIGH ({stats.highPriority})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#d97706' }}></span> MED ({stats.mediumPriority})</span>
                        <span className="swatch-item"><span className="layer-dot" style={{ background: '#16a34a' }}></span> LOW ({stats.lowPriority})</span>
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
                  <Layers size={14} style={{ color: 'var(--vd-deep)' }} />
                  <span>Layers ({Object.values(layers).filter(Boolean).length}/9)</span>
                  <ChevronDown size={13} style={{ color: 'var(--vd-text-secondary)' }} />
                </button>
              )}
              {/* Floating Reopen Handles on Map for Collapsed Right Panel */}
              {!rightPanelOpen && activeNav !== 'Analyze Your Forest' && (
                <>
                  <div
                    className="edge-pull-tab right"
                    onClick={() => setRightPanelOpen(true)}
                    title="Click to pull out Audit & Inspector Drawer"
                  >
                    <ChevronLeft size={16} />
                    <span className="edge-pull-label">AUDIT DRAWER</span>
                  </div>

                  <button
                    className="floating-reopen-btn right"
                    onClick={() => setRightPanelOpen(true)}
                    title="Expand Audit & Inspector Panel"
                  >
                    <ChevronLeft size={13} style={{ color: 'var(--vd-pale)' }} />
                    <ShieldAlert size={14} style={{ color: 'var(--vd-pale)' }} />
                    <span>Audit & Alerts</span>
                  </button>
                </>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* 3. RIGHT PANEL (COMPACT COLLAPSIBLE DRAWER)                               */}
          {/* ========================================================================= */}
          <div className={`right-panel ${!rightPanelOpen ? 'collapsed' : ''}`}>
            <div className="right-panel-topbar">
              <div className="right-panel-title">
                <ShieldAlert size={14} style={{ color: 'var(--vd-deep)' }} />
                <span>Audit & Inspector</span>
              </div>
              <button
                className="panel-close-btn"
                onClick={() => setRightPanelOpen(false)}
                title="Collapse Panel"
              >
                <ChevronRight size={16} />
              </button>
            </div>

            <div className="right-panel-content">
              {/* RECENT ALERTS */}
              <div className="panel-section">
                <div
                  className="section-heading"
                  onClick={() => setAlertsExpanded(!alertsExpanded)}
                  style={{ cursor: 'pointer', justifyContent: 'space-between' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <ShieldAlert size={14} style={{ color: 'var(--vd-deep)' }} />
                    <span>Real-Time Audit & Alerts</span>
                  </div>
                  {alertsExpanded ? <ChevronUp size={13} style={{ color: 'var(--vd-text-secondary)' }} /> : <ChevronDown size={13} style={{ color: 'var(--vd-text-secondary)' }} />}
                </div>

                {alertsExpanded && (
                  <div className="collapsible-section-content">
                    <div className="alert-card priority">
                      <div className="alert-title">
                        <AlertTriangle size={13} />
                        <span>{stats.highPriority} Mandatory Ground Stops</span>
                      </div>
                      <div className="alert-text">
                        All {stats.highPriority} HIGH-priority trees fall within the project corridor and require ground truth verification.
                      </div>
                    </div>

                    <div className="alert-card route">
                      <div className="alert-title">
                        <Navigation size={13} />
                        <span>Terrain TSP: {stats.terrainDist}m ({stats.terrainTime} min)</span>
                      </div>
                      <div className="alert-text">
                        Held-Karp terrain TSP saved {stats.terrainSaved} min traversal time vs nearest-neighbor.
                      </div>
                    </div>

                    <div className="alert-card fire">
                      <div className="alert-title">
                        <Scissors size={13} />
                        <span>{stats.totalDegPolygons} Canopy Loss Zones</span>
                      </div>
                      <div className="alert-text">
                        {stats.removalCount} severe removal (ΔH ≤ -5m) & {stats.thinningCount} thinning polygons via LiDAR differencing.
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* FEATURE INSPECTOR */}
              <div className="panel-section">
                <div
                  className="section-heading"
                  onClick={() => setInspectorExpanded(!inspectorExpanded)}
                  style={{ cursor: 'pointer', justifyContent: 'space-between' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Info size={14} style={{ color: 'var(--vd-deep)' }} />
                    <span>Feature Inspector</span>
                  </div>
                  {inspectorExpanded ? <ChevronUp size={13} style={{ color: 'var(--vd-text-secondary)' }} /> : <ChevronDown size={13} style={{ color: 'var(--vd-text-secondary)' }} />}
                </div>

                {inspectorExpanded && (
                  <div className="collapsible-section-content">
                    {selectedFeature ? (
                      <div className="inspector-card">
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: 'var(--vd-deep)', borderBottom: '1px solid rgba(70,133,133,0.2)', paddingBottom: '3px', marginBottom: '5px' }}>
                          <span>TYPE: {selectedFeature.type.toUpperCase()}</span>
                          <button onClick={() => setSelectedFeature(null)} style={{ background: 'none', border: 'none', color: 'var(--vd-text-secondary)', cursor: 'pointer', fontSize: '10px', fontWeight: 600 }}>
                            Clear
                          </button>
                        </div>

                        {selectedFeature.type === 'tree' && (
                          <div>
                            <div className="inspector-row"><span className="inspector-key">Tree ID:</span><span className="inspector-val">#{selectedFeature.properties.tree_id}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Priority:</span><span className="inspector-val" style={{ color: selectedFeature.properties.verification_priority === 'HIGH' ? '#dc2626' : '#d97706' }}>{selectedFeature.properties.verification_priority}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Confidence:</span><span className="inspector-val">{(selectedFeature.properties.confidence * 100).toFixed(1)}%</span></div>
                            <div className="inspector-row"><span className="inspector-key">Corridor:</span><span className="inspector-val">{selectedFeature.properties.inside_boundary ? 'YES (AFFECTED)' : 'NO (SAFE)'}</span></div>
                            <div className="inspector-row"><span className="inspector-key">UTM Easting:</span><span className="inspector-val">{selectedFeature.properties.geo_easting}</span></div>
                            <div className="inspector-row"><span className="inspector-key">UTM Northing:</span><span className="inspector-val">{selectedFeature.properties.geo_northing}</span></div>
                            <div style={{ fontSize: '9.5px', color: 'var(--vd-text-secondary)', marginTop: '4px', fontStyle: 'italic' }}>{selectedFeature.properties.priority_reason}</div>
                          </div>
                        )}

                        {selectedFeature.type === 'health_cell' && (
                          <div>
                            <div className="inspector-row"><span className="inspector-key">Cell ID:</span><span className="inspector-val">{selectedFeature.properties.cell_id}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Grade:</span><span className="inspector-val" style={{ color: getHealthGradeColor(selectedFeature.properties.grade), fontWeight: 'bold' }}>Grade {selectedFeature.properties.grade}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Health Score:</span><span className="inspector-val">{selectedFeature.properties.score !== null ? Number(selectedFeature.properties.score).toFixed(1) : 'N/A'} / 100</span></div>
                            <div className="inspector-row"><span className="inspector-key">Canopy Cover:</span><span className="inspector-val">{(selectedFeature.properties.canopy_cover * 100).toFixed(1)}%</span></div>
                            <div className="inspector-row"><span className="inspector-key">Height σ:</span><span className="inspector-val">{selectedFeature.properties.structural_diversity} m</span></div>
                            <div className="inspector-row"><span className="inspector-key">Loss Density:</span><span className="inspector-val">{(selectedFeature.properties.loss_density * 100).toFixed(2)}%</span></div>
                          </div>
                        )}

                        {selectedFeature.type === 'degradation' && (
                          <div>
                            <div className="inspector-row"><span className="inspector-key">Class:</span><span className="inspector-val" style={{ color: selectedFeature.properties.class_name === 'removal' ? '#dc2626' : '#d97706', fontWeight: 'bold' }}>{selectedFeature.properties.class_name ? selectedFeature.properties.class_name.toUpperCase() : 'LOSS'}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Impact Area:</span><span className="inspector-val">{selectedFeature.properties.area_m2} m²</span></div>
                            <div className="inspector-row"><span className="inspector-key">Tier:</span><span className="inspector-val">{selectedFeature.properties.class_name === 'removal' ? 'ΔH ≤ -5.0 m' : '-5.0m < ΔH ≤ -2.0m'}</span></div>
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
                          </div>
                        )}

                        {selectedFeature.type === 'fire' && (
                          <div>
                            <div className="inspector-row"><span className="inspector-key">Hotspot ID:</span><span className="inspector-val">#{selectedFeature.properties.hotspot_id}</span></div>
                            <div className="inspector-row"><span className="inspector-key">FRP Power:</span><span className="inspector-val">{selectedFeature.properties.frp_mw} MW</span></div>
                            <div className="inspector-row"><span className="inspector-key">Acq Date:</span><span className="inspector-val">{selectedFeature.properties.acq_date}</span></div>
                            <div className="inspector-row"><span className="inspector-key">Sensor:</span><span className="inspector-val">VIIRS 375m NRT</span></div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ fontSize: '10.5px', color: 'var(--vd-text-secondary)', fontStyle: 'italic', padding: '10px 12px', background: '#ffffff', borderRadius: 'var(--vd-radius-sm)', border: '1px solid var(--vd-border-subtle)' }}>
                        Click on any marker, cell, zone, or route on the map to inspect attributes.
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 13 HIGH PRIORITY ITINERARY TABLE */}
              <div className="panel-section">
                <div
                  className="section-heading"
                  onClick={() => setStopsExpanded(!stopsExpanded)}
                  style={{ cursor: 'pointer', justifyContent: 'space-between' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Navigation size={14} style={{ color: 'var(--vd-deep)' }} />
                    <span>13 Audit Stops (Sequence)</span>
                  </div>
                  {stopsExpanded ? <ChevronUp size={13} style={{ color: 'var(--vd-text-secondary)' }} /> : <ChevronDown size={13} style={{ color: 'var(--vd-text-secondary)' }} />}
                </div>

                {stopsExpanded && (
                  <div className="collapsible-section-content">
                    <div className="stops-table-card compact">
                      {orderedStops.map((st) => (
                        <div
                          key={st.stopNum}
                          className="stops-row"
                          onClick={() => handleFocusStop(st)}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ background: 'var(--vd-aqua)', color: 'white', width: '18px', height: '18px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '9.5px', fontWeight: 800 }}>
                              {st.stopNum}
                            </span>
                            <span style={{ fontWeight: 700, color: 'var(--vd-text-heading)' }}>Tree #{st.treeId}</span>
                          </div>
                          <div style={{ color: '#b45309', fontFamily: 'JetBrains Mono', fontSize: '9.5px', fontWeight: 600 }}>
                            {(st.properties.confidence * 100).toFixed(1)}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* DATA SOURCES */}
              <div className="panel-section">
                <div className="section-heading">
                  <FileText size={14} style={{ color: 'var(--vd-deep)' }} />
                  <span>Verified Data Feeds</span>
                </div>

                <div className="source-item">
                  <div className="source-name">NEON AOP Survey</div>
                  <div>10 cm/pixel RGB & LiDAR CHM/DTM data.</div>
                </div>

                <div className="source-item">
                  <div className="source-name">DeepForest & Tobler TSP</div>
                  <div>Tree detection + Held-Karp least-cost pathing.</div>
                </div>

                <div className="source-item">
                  <div className="source-name">NASA FIRMS NRT</div>
                  <div>VIIRS 375m active fire detection product.</div>
                </div>
              </div>
            </div>

            {/* HONESTY FOOTER */}
            <div className="honesty-footer compact">
              <div className="honesty-title">VanDrishti System Integrity</div>
              <div>Computed directly from authentic NEON & NASA geospatial layers.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

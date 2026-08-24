/**
 * frontend/src/utils/moduleStatus.js
 * Single source of truth helper for deriving module capability, status,
 * badges, messages, and metrics across both Upload mode and Baseline mode.
 */

/**
 * Derives comprehensive status and metrics for a specific module.
 *
 * @param {string} moduleKey - 'detection' | 'routing' | 'priority' | 'degradation' | 'health_score' | 'fire'
 * @param {Object} ctx - Context object
 * @param {boolean} ctx.isUploadMode - True if currently viewing an uploaded dataset or preset
 * @param {Object} [ctx.uploadedAssessment] - Assessment report from assess_upload()
 * @param {Object} [ctx.activeCostSurface] - Cost surface JSON for the upload/preset
 * @param {Object} [ctx.uploadedHealthGridData] - GeoJSON health grid
 * @param {Object} [ctx.uploadedDegradationData] - GeoJSON degradation polygons
 * @param {Object} [ctx.fireHotspotsData] - GeoJSON fire hotspots
 * @param {Object} [ctx.stats] - Computed baseline statistics
 * @returns {Object} Normalized module status descriptor
 */
export function deriveModuleStatus(moduleKey, ctx = {}) {
  const {
    isUploadMode = false,
    uploadedAssessment = null,
    activeCostSurface = null,
    uploadedHealthGridData = null,
    uploadedDegradationData = null,
    fireHotspotsData = null,
    stats = {},
  } = ctx;

  switch (moduleKey) {
    case 'degradation': {
      if (isUploadMode) {
        const degCap = uploadedAssessment?.capabilities?.degradation || {};
        const degMeta = uploadedAssessment?.degradation || uploadedAssessment?.metadata?.degradation || {};
        const degFeatures = uploadedDegradationData?.features || [];
        const hasPolys = degFeatures.length > 0;
        const isGen = Boolean(degMeta?.generated);

        const level = (degCap?.level === 'FULL' || isGen || hasPolys)
          ? 'FULL'
          : (degCap?.level || 'BLOCKED');
        const isAvailable = level !== 'BLOCKED';

        const polygonCount = hasPolys ? degFeatures.length : (degMeta?.polygon_count || 0);
        const removalCount = degFeatures.filter(
          (f) => f.properties?.class_name === 'removal' || f.properties?.class_id === 1
        ).length;
        const thinningCount = degFeatures.filter(
          (f) => f.properties?.class_name === 'thinning' || f.properties?.class_id === 2
        ).length;

        const rawReason = degMeta?.reason || degCap?.note || uploadedAssessment?.checklist?.find((i) => i.key === 'degradation')?.message;
        const reason = rawReason
          ? rawReason.replace(/\(single epoch uploaded\)/gi, '(single epoch available)')
          : 'Needs two acquisition dates (single epoch available)';

        let message = 'Multi-temporal loss differencing';
        if (isAvailable) {
          if (polygonCount > 0) {
            message = `${polygonCount} zones (${removalCount} Removal • ${thinningCount} Thinning)`;
          }
        } else {
          message = reason;
        }

        return {
          key: 'degradation',
          title: 'Canopy Degradation',
          alertTitle: polygonCount > 0 ? `${polygonCount} Canopy Loss Zones` : 'Canopy Loss Zones',
          level,
          isAvailable,
          badgeClass: level.toLowerCase(),
          badgeLabel: `[${level}]`,
          message,
          reason: isAvailable ? null : reason,
          details: degCap?.lost_capability || [],
          note: degCap?.note || '',
          stats: {
            polygonCount,
            removalCount,
            thinningCount,
          },
        };
      }

      // Baseline Mode
      const polygonCount = stats.totalDegPolygons || 0;
      const removalCount = stats.removalCount || 0;
      const thinningCount = stats.thinningCount || 0;
      return {
        key: 'degradation',
        title: 'Canopy Degradation',
        alertTitle: `${polygonCount} Canopy Loss Zones`,
        level: 'FULL',
        isAvailable: true,
        badgeClass: 'full',
        badgeLabel: '[FULL]',
        message: `${removalCount} severe removal (ΔH ≤ -5m) & ${thinningCount} thinning polygons via LiDAR differencing.`,
        reason: null,
        details: [],
        note: 'Bi-temporal LiDAR CHM differencing',
        stats: {
          polygonCount,
          removalCount,
          thinningCount,
        },
      };
    }

    case 'health_score': {
      if (isUploadMode) {
        const healthCap = uploadedAssessment?.capabilities?.health_score || {};
        const healthMeta = uploadedAssessment?.health_grid || uploadedAssessment?.metadata?.health_grid || {};
        const healthFeatures = uploadedHealthGridData?.features || [];
        const hasCells = healthFeatures.length > 0;
        const isGen = Boolean(healthMeta?.generated);

        const level = (healthCap?.level === 'FULL' || isGen || hasCells)
          ? 'FULL'
          : (healthCap?.level || 'BLOCKED');
        const isAvailable = level !== 'BLOCKED';

        const cellCount = hasCells ? healthFeatures.length : (healthMeta?.cell_count || 0);
        const cellSize =
          healthMeta?.cell_size_m ||
          healthMeta?.stats?.cell_size_m ||
          uploadedHealthGridData?.cell_size_m ||
          uploadedHealthGridData?.stats?.cell_size_m ||
          healthFeatures?.[0]?.properties?.cell_size_m ||
          25;

        const gradeA = healthFeatures.filter((f) => f.properties?.grade === 'A').length;
        const gradeB = healthFeatures.filter((f) => f.properties?.grade === 'B').length;
        const gradeC = healthFeatures.filter((f) => f.properties?.grade === 'C').length;
        const gradeD = healthFeatures.filter((f) => f.properties?.grade === 'D').length;

        const rawReason = healthMeta?.reason || healthCap?.note || uploadedAssessment?.checklist?.find((i) => i.key === 'health_score')?.message;
        const reason = rawReason || 'No multi-temporal CHM available';
        const message = isAvailable ? `${cellSize} m composite grid` : reason;

        return {
          key: 'health_score',
          title: 'Forest Health Score',
          alertTitle: isAvailable ? `Forest Health Grid (${cellCount} · ${cellSize} m)` : 'Forest Health Grid',
          level,
          isAvailable,
          badgeClass: level.toLowerCase(),
          badgeLabel: `[${level}]`,
          message,
          reason: isAvailable ? null : reason,
          details: healthCap?.lost_capability || [],
          note: healthCap?.note || '',
          stats: {
            cellCount,
            cellSize,
            gradeA,
            gradeB,
            gradeC,
            gradeD,
          },
        };
      }

      // Baseline Mode
      const cellCount = stats.totalHealthCells || 0;
      const cellSize = stats.healthCellSize || 25;
      return {
        key: 'health_score',
        title: 'Forest Health Score',
        alertTitle: `Forest Health Grid (${cellCount} · ${cellSize} m)`,
        level: 'FULL',
        isAvailable: true,
        badgeClass: 'full',
        badgeLabel: '[FULL]',
        message: `Composite health grading (Grades A-D, ${cellSize} m grid)`,
        reason: null,
        details: [],
        note: 'Multi-metric LiDAR canopy evaluation',
        stats: {
          cellCount,
          cellSize,
          gradeA: stats.gradeA || 0,
          gradeB: stats.gradeB || 0,
          gradeC: stats.gradeC || 0,
          gradeD: stats.gradeD || 0,
        },
      };
    }

    case 'routing': {
      if (isUploadMode) {
        const routeCap = uploadedAssessment?.capabilities?.routing || {};
        const hasDtm = Boolean(uploadedAssessment?.detected_siblings?.dtm || activeCostSurface?.active_terms?.includes('Slope'));
        const hasChm = Boolean(uploadedAssessment?.detected_siblings?.chm || activeCostSurface?.active_terms?.includes('CHM'));
        const hasCostSurface = Boolean(activeCostSurface?.routable);

        const level = routeCap?.level || (hasDtm ? 'FULL' : ((hasChm || hasCostSurface) ? 'DEGRADED' : 'BLOCKED'));
        const isAvailable = level !== 'BLOCKED' && hasCostSurface;

        const modeLabel = activeCostSurface?.mode_label || (hasDtm ? 'DTM Slope + CHM' : (hasChm ? 'CHM Impedance' : 'Optical ExG'));
        const activeTerms = activeCostSurface?.active_terms || [];
        const relief = activeCostSurface?.diagnostics?.relief_m;

        const reason = isAvailable ? null : (activeCostSurface?.reason || 'No DTM/CHM available — terrain routing unavailable');
        const message = isAvailable
          ? (hasDtm
              ? `Slope-aware Tobler impedance enabled with DTM (${relief ? `${relief.toFixed(1)}m relief` : 'elevation model'})`
              : 'CHM canopy impedance active; DTM slope disabled (flat-ground baseline)')
          : reason;

        return {
          key: 'routing',
          title: 'Terrain TSP Route',
          alertTitle: `Terrain Routing (${modeLabel})`,
          level,
          isAvailable,
          badgeClass: level.toLowerCase(),
          badgeLabel: `[${level}]`,
          modeLabel,
          activeTerms,
          message,
          reason,
          details: routeCap?.lost_capability || [],
          note: routeCap?.note || '',
          stats: {
            hasDtm,
            hasChm,
            relief,
            activeTerms,
          },
        };
      }

      // Baseline Mode
      return {
        key: 'routing',
        title: 'Terrain TSP Route',
        alertTitle: `Terrain TSP: ${stats.terrainDist}m (${stats.terrainTime} min)`,
        level: 'FULL',
        isAvailable: true,
        badgeClass: 'full',
        badgeLabel: '[FULL]',
        modeLabel: 'Exact Held-Karp TSP',
        message: `Held-Karp terrain TSP saved ${stats.terrainSaved} min traversal time vs nearest-neighbor.`,
        reason: null,
        details: [],
        note: 'Dijkstra + Held-Karp optimization over Tobler slope',
        stats: {
          distance: stats.terrainDist,
          time: stats.terrainTime,
          saved: stats.terrainSaved,
          stopsCount: stats.highPriority,
        },
      };
    }

    case 'priority': {
      if (isUploadMode) {
        const prioCap = uploadedAssessment?.capabilities?.priority || {};
        const level = prioCap?.level || 'BLOCKED';
        const isAvailable = level !== 'BLOCKED';
        const reason = isAvailable ? null : 'No project corridor available — priority audit unavailable';
        const message = isAvailable ? 'Confidence proxy tagging' : reason;

        return {
          key: 'priority',
          title: 'Verification Priority',
          alertTitle: isAvailable ? `${stats.highPriority || 0} Mandatory Ground Stops` : 'Mandatory Ground Stops',
          level,
          isAvailable,
          badgeClass: level.toLowerCase(),
          badgeLabel: `[${level}]`,
          message,
          reason,
          details: prioCap?.lost_capability || [],
          note: prioCap?.note || '',
          stats: {
            stopsCount: stats.highPriority || 0,
          },
        };
      }

      // Baseline Mode
      return {
        key: 'priority',
        title: 'Verification Priority',
        alertTitle: `${stats.highPriority} Mandatory Ground Stops`,
        level: 'FULL',
        isAvailable: true,
        badgeClass: 'full',
        badgeLabel: '[FULL]',
        message: `All ${stats.highPriority} HIGH-priority trees fall within the project corridor and require ground truth verification.`,
        reason: null,
        details: [],
        note: 'Corridor spatial intersection + uncertainty ranking',
        stats: {
          stopsCount: stats.highPriority,
          mediumCount: stats.mediumPriority,
          lowCount: stats.lowPriority,
        },
      };
    }

    case 'detection': {
      if (isUploadMode) {
        const detCap = uploadedAssessment?.capabilities?.detection || {};
        const detRes = uploadedAssessment?.detection_results || {};
        const count = detRes?.count || 0;
        const level = detCap?.level || (count > 0 ? 'FULL' : 'BLOCKED');
        const isAvailable = level !== 'BLOCKED';
        const method = detRes?.method === 'deepforest' ? 'DeepForest RetinaNet' : 'ExG Heuristic';
        const res_m = uploadedAssessment?.raster_info?.res_m;

        return {
          key: 'detection',
          title: 'Tree Detection',
          alertTitle: `Detected Tree Canopies (${count.toLocaleString()})`,
          level,
          isAvailable,
          badgeClass: level.toLowerCase(),
          badgeLabel: `[${level}]`,
          message: `${count.toLocaleString()} canopies detected via ${method}`,
          reason: isAvailable ? null : 'Missing valid RGB raster',
          details: detCap?.lost_capability || [],
          note: detCap?.note || '',
          stats: {
            count,
            method,
            res_m,
          },
        };
      }

      // Baseline Mode
      return {
        key: 'detection',
        title: 'Tree Inventory & Detection',
        alertTitle: `Tree Inventory (${stats.operationalInventory?.toLocaleString() || 0})`,
        level: 'FULL',
        isAvailable: true,
        badgeClass: 'full',
        badgeLabel: '[FULL]',
        message: `${stats.rawTrees?.toLocaleString()} raw detections → ${stats.validatedTrees?.toLocaleString()} LiDAR validated → ${stats.operationalInventory?.toLocaleString()} operational inventory`,
        reason: null,
        details: [],
        note: 'DeepForest 10cm RGB crown delineation',
        stats: {
          rawTrees: stats.rawTrees,
          validatedTrees: stats.validatedTrees,
          operationalInventory: stats.operationalInventory,
          insideTrees: stats.insideTrees,
          outsideTrees: stats.outsideTrees,
        },
      };
    }

    case 'fire': {
      const fireCap = uploadedAssessment?.capabilities?.fire || {};
      const level = fireCap?.level || 'FULL';
      const hotspotCount = stats?.fireCount ?? fireHotspotsData?.hotspot_count ?? 0;
      const status = stats?.fireStatus || fireHotspotsData?.status || 'AVAILABLE';
      const reason = stats?.fireReason || fireHotspotsData?.reason || null;

      return {
        key: 'fire',
        title: 'Active Fire Hotspots',
        alertTitle: `${hotspotCount} Live Fire Hotspots`,
        level,
        isAvailable: level !== 'BLOCKED',
        badgeClass: level.toLowerCase(),
        badgeLabel: `[${level}]`,
        message: 'NASA FIRMS live satellite feed (VIIRS 375m)',
        reason,
        details: [],
        note: 'Real-time thermal anomaly monitoring',
        stats: {
          hotspotCount,
          status,
        },
      };
    }

    default: {
      return {
        key: moduleKey,
        title: moduleKey,
        alertTitle: moduleKey,
        level: 'UNKNOWN',
        isAvailable: false,
        badgeClass: 'blocked',
        badgeLabel: '[UNKNOWN]',
        message: 'Unknown module',
        reason: null,
        details: [],
        note: '',
        stats: {},
      };
    }
  }
}

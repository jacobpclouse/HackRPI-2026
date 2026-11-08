import { state } from "../state.js";

const GAP = "#f5a524";
const KN_KM = 1.852;

let ringEntities = [];

export function clearReach() {
  if (!state.viewer) {
    ringEntities = [];
    return;
  }
  for (const entity of ringEntities) state.viewer.entities.remove(entity);
  ringEntities = [];
}

export function reachRadiusM(hours, speedKn) {
  return Math.max(0, Number(hours) * Number(speedKn) * KN_KM * 1000);
}

export function drawReach(lat, lon, hours, speeds) {
  clearReach();
  const viewer = state.viewer;
  if (!viewer) return;
  const gap = Cesium.Color.fromCssColorString(GAP);
  const bands = [
    { kn: speeds.fast, fill: 0.04, line: 0.35, label: "20 kn" },
    { kn: speeds.typical, fill: 0.07, line: 0.6, label: "12 kn" },
    { kn: speeds.slow, fill: 0.12, line: 0.95, label: "6 kn" },
  ];
  for (const band of bands) {
    const radius = reachRadiusM(hours, band.kn);
    if (radius < 80) continue;
    ringEntities.push(viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      ellipse: {
        semiMinorAxis: radius,
        semiMajorAxis: radius,
        material: gap.withAlpha(band.fill),
        outline: true,
        outlineColor: gap.withAlpha(band.line),
        height: 0,
      },
    }));
    const dlat = radius / 111320;
    ringEntities.push(viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat + dlat),
      label: {
        text: band.label,
        font: "11px JetBrains Mono, monospace",
        fillColor: gap,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -8),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    }));
  }
}

export function flyToReach(lat, lon, hours, speeds, satPos) {
  const radius = reachRadiusM(hours, speeds.fast || 20);
  const dlat = Math.max(radius, 80000) / 111320;
  const positions = [
    Cesium.Cartesian3.fromDegrees(lon, lat),
    Cesium.Cartesian3.fromDegrees(lon, lat + dlat),
    Cesium.Cartesian3.fromDegrees(lon, lat - dlat),
  ];
  if (satPos) positions.push(Cesium.Cartesian3.clone(satPos));
  const sphere = Cesium.BoundingSphere.fromPoints(positions);
  state.viewer.trackedEntity = undefined;
  state.viewer.camera.flyToBoundingSphere(sphere, {
    duration: 2.2,
    offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-32), Math.max(sphere.radius * 2.4, 5e6)),
    easingFunction: Cesium.EasingFunction.CUBIC_IN_OUT,
  });
}

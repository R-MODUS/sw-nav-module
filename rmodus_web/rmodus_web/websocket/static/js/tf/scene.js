/**
 * WebGL scéna TF (Three.js). Načítá se líně z index.js.
 *
 * - Hierarchie Object3D kopíruje strom TF; matice rámů se skládají přímo
 *   v rAF smyčce (matrixAutoUpdate = false) jen u rámů se změněnou revizí.
 * - Scéna je vyjádřena v pevném rámu: kořen TF lesa dostane inverzi
 *   world matice pevného rámu.
 * - Kreslí se jen na vyžádání (data / kamera / zdraví / výběr).
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';
import { HEALTH } from './store.js';

const HEALTH_COLORS = {
    [HEALTH.OK]: 0x4ade80,
    [HEALTH.STATIC]: 0x9aa9bd,
    [HEALTH.WARN]: 0xf59e0b,
    [HEALTH.ERROR]: 0xef4444,
    [HEALTH.ROOT]: 0x00d4ff,
};
const LINK_DIM = 0.55;
const SELECT_COLOR = 0x00d4ff;
const BACKGROUND = 0x05080d;
const HEALTH_TICK_MS = 200;
const DRAG_THRESHOLD_PX = 6;
const AXIS_THICKNESS = 0.035;
const MARKER_RADIUS = 0.1;
const ORTHO_HALF_HEIGHT = 0.9;
const PLACEHOLDER_BASE_SIZE = [0.4, 0.3, 0.1];

const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _one = new THREE.Vector3(1, 1, 1);
const _mat = new THREE.Matrix4();
const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _color = new THREE.Color();

function buildAxesGeometry() {
    const t = AXIS_THICKNESS;
    const parts = [
        { size: [1, t, t], offset: [0.5, 0, 0], color: 0xef4444 },
        { size: [t, 1, t], offset: [0, 0.5, 0], color: 0x22c55e },
        { size: [t, t, 1], offset: [0, 0, 0.5], color: 0x3b82f6 },
    ];
    const positions = [];
    const colors = [];
    parts.forEach(({ size, offset, color }) => {
        const box = new THREE.BoxGeometry(...size).translate(...offset).toNonIndexed();
        const array = box.getAttribute('position').array;
        _color.setHex(color);
        for (let i = 0; i < array.length; i += 3) {
            positions.push(array[i], array[i + 1], array[i + 2]);
            colors.push(_color.r, _color.g, _color.b);
        }
        box.dispose();
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geometry.computeBoundingSphere();
    return geometry;
}

function buildGrid(size, divisions, color, opacity) {
    const grid = new THREE.GridHelper(size, divisions, color, color);
    grid.rotation.x = Math.PI / 2;
    grid.material.transparent = true;
    grid.material.opacity = opacity;
    grid.material.depthWrite = false;
    return grid;
}

function buildBox(size, fillColor, fillOpacity, edgeColor) {
    const group = new THREE.Group();
    const geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
    const fill = new THREE.Mesh(
        geometry,
        new THREE.MeshBasicMaterial({ color: fillColor, transparent: true, opacity: fillOpacity, depthWrite: false }),
    );
    const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: edgeColor }),
    );
    group.add(fill, edges);
    return group;
}

/** URDF convention: cylinder axis = z, size = [radius, length]; rpy applied as fixed XYZ. */
function buildPart(part) {
    const size = Array.isArray(part.size) ? part.size : [];
    const color = new THREE.Color(part.color || '#94a3b8').getHex();
    let geometry;
    if (part.shape === 'cylinder' && size.length >= 2) {
        geometry = new THREE.CylinderGeometry(size[0], size[0], size[1], 24).rotateX(Math.PI / 2);
    } else if (part.shape === 'box' && size.length >= 3) {
        geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
    } else {
        return null;
    }
    const group = new THREE.Group();
    group.add(
        new THREE.Mesh(
            geometry,
            new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, depthWrite: false }),
        ),
        new THREE.LineSegments(
            new THREE.EdgesGeometry(geometry, 30),
            new THREE.LineBasicMaterial({ color }),
        ),
    );
    const xyz = Array.isArray(part.xyz) ? part.xyz : [0, 0, 0];
    const rpy = Array.isArray(part.rpy) ? part.rpy : [0, 0, 0];
    group.position.set(xyz[0] || 0, xyz[1] || 0, xyz[2] || 0);
    group.rotation.set(rpy[0] || 0, rpy[1] || 0, rpy[2] || 0, 'ZYX');
    group.userData.frame = String(part.frame || 'base_link');
    group.name = String(part.name || group.userData.frame);
    return group;
}

function disposeObject(root) {
    root.traverse((obj) => {
        if (obj.geometry) {
            obj.geometry.dispose();
        }
        if (obj.material) {
            (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach((m) => m.dispose());
        }
    });
}

export class TfScene {
    constructor(container, store, { onPick } = {}) {
        this.container = container;
        this.store = store;
        this.onPick = onPick || (() => {});

        this.nodes = new Map();
        this.pickTargets = [];
        this.selectedId = null;
        this.fixedFrameId = store.rootHint;
        this.showLabels = false;
        this.axisScale = 0.12;
        this.mode = '3d';
        this.robotModel = null;

        this.topologyVersion = -1;
        this.dataVersion = -1;
        this.worldDirty = true;
        this.linkColorsDirty = true;
        this.needsRender = true;
        this.lastHealthTick = 0;
        this.disposed = false;

        this._initRenderer();
        this._initScene();
        this._initCameras();
        this._initPicking();

        this.resizeObserver = new ResizeObserver(() => this._resize());
        this.resizeObserver.observe(container);
        this._resize();

        this._tick = this._tick.bind(this);
        this.raf = requestAnimationFrame(this._tick);
    }

    /* ---------- init ---------- */

    _initRenderer() {
        this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        this.renderer.setClearColor(BACKGROUND, 1);
        this.renderer.domElement.classList.add('tf-canvas');
        this.container.appendChild(this.renderer.domElement);

        this.labelRenderer = new CSS2DRenderer();
        this.labelRenderer.domElement.classList.add('tf-label-layer');
        this.container.appendChild(this.labelRenderer.domElement);
    }

    _initScene() {
        this.scene = new THREE.Scene();
        this.scene.add(buildGrid(4, 40, 0x334155, 0.35));
        this.scene.add(buildGrid(40, 40, 0x475569, 0.55));

        this.tfRoot = new THREE.Group();
        this.tfRoot.matrixAutoUpdate = false;
        this.scene.add(this.tfRoot);

        this.axesGeometry = buildAxesGeometry();
        this.axesMaterial = new THREE.MeshBasicMaterial({ vertexColors: true });
        this.markerGeometry = new THREE.SphereGeometry(MARKER_RADIUS, 16, 12);
        this.healthMaterials = {};
        Object.entries(HEALTH_COLORS).forEach(([health, color]) => {
            this.healthMaterials[health] = new THREE.MeshBasicMaterial({ color });
        });

        this.halo = new THREE.Mesh(
            this.markerGeometry,
            new THREE.MeshBasicMaterial({ color: SELECT_COLOR, transparent: true, opacity: 0.35, depthWrite: false }),
        );
        this.halo.matrixAutoUpdate = false;
        this.halo.renderOrder = 2;

        this.linkCapacity = 0;
        this.links = new THREE.LineSegments(
            new THREE.BufferGeometry(),
            new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9 }),
        );
        this.links.frustumCulled = false;
        this.scene.add(this.links);

        this.robotGroup = null;
        this.moduleGroup = null;
        this.partGroups = [];
    }

    _initCameras() {
        const dom = this.renderer.domElement;

        this.perspCamera = new THREE.PerspectiveCamera(50, 1, 0.01, 1000);
        this.perspCamera.up.set(0, 0, 1);
        this.perspCamera.position.set(-0.9, -0.9, 0.75);
        this.perspControls = new OrbitControls(this.perspCamera, dom);
        this.perspControls.enableDamping = true;
        this.perspControls.dampingFactor = 0.15;
        this.perspControls.minDistance = 0.05;
        this.perspControls.maxDistance = 200;
        this.perspControls.saveState();

        this.orthoCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 1000);
        this.orthoCamera.up.set(0, 1, 0);
        this.orthoCamera.position.set(0, 0, 50);
        this.orthoCamera.lookAt(0, 0, 0);
        this.orthoControls = new OrbitControls(this.orthoCamera, dom);
        this.orthoControls.enableRotate = false;
        this.orthoControls.screenSpacePanning = true;
        this.orthoControls.enableDamping = true;
        this.orthoControls.dampingFactor = 0.15;
        this.orthoControls.minZoom = 0.05;
        this.orthoControls.maxZoom = 80;
        this.orthoControls.mouseButtons = {
            LEFT: THREE.MOUSE.PAN,
            MIDDLE: THREE.MOUSE.DOLLY,
            RIGHT: THREE.MOUSE.PAN,
        };
        this.orthoControls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN };
        this.orthoControls.saveState();

        const requestRender = () => {
            this.needsRender = true;
        };
        this.perspControls.addEventListener('change', requestRender);
        this.orthoControls.addEventListener('change', requestRender);
        this._applyCameraMode();
    }

    _initPicking() {
        const dom = this.renderer.domElement;
        this.raycaster = new THREE.Raycaster();
        this.pointer = new THREE.Vector2();
        this.pointerDown = null;

        this._onPointerDown = (event) => {
            this.pointerDown = event.isPrimary ? { x: event.clientX, y: event.clientY } : null;
        };
        this._onPointerUp = (event) => {
            const down = this.pointerDown;
            this.pointerDown = null;
            if (!down || !event.isPrimary) {
                return;
            }
            if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > DRAG_THRESHOLD_PX) {
                return;
            }
            this.onPick(this._pickAt(event.clientX, event.clientY));
        };
        dom.addEventListener('pointerdown', this._onPointerDown);
        dom.addEventListener('pointerup', this._onPointerUp);
    }

    /* ---------- public API ---------- */

    setSelected(frameId) {
        const prev = this.nodes.get(this.selectedId);
        this.selectedId = frameId || null;
        if (prev) {
            this._applyNodeScale(prev);
            this._syncLabel(prev);
        }
        this.halo.removeFromParent();
        const node = this.nodes.get(this.selectedId);
        if (node) {
            node.group.add(this.halo);
            this._applyNodeScale(node);
            this._syncLabel(node);
        }
        this.needsRender = true;
    }

    setFixedFrame(frameId) {
        this.fixedFrameId = frameId || this.store.rootHint;
        this.worldDirty = true;
    }

    setCameraMode(mode) {
        const next = mode === '2d' ? '2d' : '3d';
        if (next === this.mode) {
            return;
        }
        if (next === '2d') {
            const target = this.perspControls.target;
            this.orthoControls.target.set(target.x, target.y, 0);
            this.orthoCamera.position.set(target.x, target.y, 50);
        }
        this.mode = next;
        this._applyCameraMode();
        this._resize();
    }

    setShowLabels(show) {
        this.showLabels = Boolean(show);
        this.nodes.forEach((node) => this._syncLabel(node));
        this.needsRender = true;
    }

    setAxisScale(scale) {
        this.axisScale = Math.max(0.01, Number(scale) || 0.12);
        this.nodes.forEach((node) => this._applyNodeScale(node));
        this.needsRender = true;
    }

    setRobotModel(model) {
        this.robotModel = model || {};
        [this.robotGroup, this.moduleGroup, ...this.partGroups].forEach((group) => {
            if (group) {
                group.removeFromParent();
                disposeObject(group);
            }
        });
        const parts = Array.isArray(this.robotModel.parts) ? this.robotModel.parts : [];
        this.partGroups = parts.map(buildPart).filter(Boolean);

        const base = this.robotModel.base_link;
        const baseSize = base && Array.isArray(base.size) ? base.size : PLACEHOLDER_BASE_SIZE;
        this.robotGroup = buildBox(baseSize, 0x64748b, 0.18, 0x94a3b8);

        const module = this.robotModel.rmodus_module;
        this.moduleGroup = module && Array.isArray(module.size)
            ? buildBox(module.size, 0x00d4ff, 0.12, 0x00d4ff)
            : null;

        this._attachRobotModel();
        this.needsRender = true;
    }

    resetView() {
        this.activeControls.reset();
        this.needsRender = true;
    }

    focusFrame(frameId) {
        const node = this.nodes.get(frameId);
        if (!node) {
            return;
        }
        node.group.getWorldPosition(_a);
        const controls = this.activeControls;
        _b.copy(_a).sub(controls.target);
        if (this.mode === '2d') {
            _b.z = 0;
        }
        controls.target.add(_b);
        controls.object.position.add(_b);
        controls.update();
        this.needsRender = true;
    }

    dispose() {
        if (this.disposed) {
            return;
        }
        this.disposed = true;
        cancelAnimationFrame(this.raf);
        this.resizeObserver.disconnect();
        const dom = this.renderer.domElement;
        dom.removeEventListener('pointerdown', this._onPointerDown);
        dom.removeEventListener('pointerup', this._onPointerUp);
        this.perspControls.dispose();
        this.orthoControls.dispose();

        this.halo.removeFromParent();
        this.halo.material.dispose();
        [this.robotGroup, this.moduleGroup, ...this.partGroups].forEach((group) => group && disposeObject(group));
        this.scene.children
            .filter((obj) => obj !== this.tfRoot)
            .forEach((obj) => disposeObject(obj));
        this.axesGeometry.dispose();
        this.axesMaterial.dispose();
        this.markerGeometry.dispose();
        Object.values(this.healthMaterials).forEach((m) => m.dispose());

        this.renderer.dispose();
        this.renderer.forceContextLoss();
        dom.remove();
        this.labelRenderer.domElement.remove();
    }

    /* ---------- render loop ---------- */

    _tick(time) {
        if (this.disposed) {
            return;
        }
        if (!this.container.isConnected) {
            this.dispose();
            return;
        }
        this.raf = requestAnimationFrame(this._tick);

        if (this.store.topologyVersion !== this.topologyVersion) {
            this.topologyVersion = this.store.topologyVersion;
            this._syncTopology();
        }
        if (this.store.dataVersion !== this.dataVersion || this.worldDirty) {
            this.dataVersion = this.store.dataVersion;
            this._applyTransforms();
        }
        if (time - this.lastHealthTick >= HEALTH_TICK_MS) {
            this.lastHealthTick = time;
            this._updateHealth();
        }
        this.activeControls.update();

        if (this.needsRender) {
            this.needsRender = false;
            this.renderer.render(this.scene, this.activeCamera);
            this.labelRenderer.render(this.scene, this.activeCamera);
        }
    }

    /* ---------- TF graph ---------- */

    _createNode(id) {
        const group = new THREE.Group();
        group.name = id;
        group.matrixAutoUpdate = false;
        group.userData.frameId = id;

        const axes = new THREE.Mesh(this.axesGeometry, this.axesMaterial);
        axes.matrixAutoUpdate = false;
        axes.userData.frameId = id;

        const marker = new THREE.Mesh(this.markerGeometry, this.healthMaterials[HEALTH.ROOT]);
        marker.matrixAutoUpdate = false;
        marker.userData.frameId = id;

        group.add(axes, marker);
        const node = { id, group, axes, marker, label: null, health: null, rev: -1 };
        this._applyNodeScale(node);
        return node;
    }

    _syncTopology() {
        const store = this.store;
        store.frames.forEach((_entry, id) => {
            if (!this.nodes.has(id)) {
                this.nodes.set(id, this._createNode(id));
            }
        });
        this.nodes.forEach((node, id) => {
            if (!store.has(id)) {
                node.group.removeFromParent();
                node.label?.element.remove();
                this.nodes.delete(id);
            }
        });

        const { roots, children } = store.forest();
        roots.forEach((id) => this.tfRoot.add(this.nodes.get(id).group));
        children.forEach((kids, parentId) => {
            const parent = this.nodes.get(parentId);
            kids.forEach((kid) => parent.group.add(this.nodes.get(kid).group));
        });

        this.pickTargets = [];
        this.nodes.forEach((node) => {
            this.pickTargets.push(node.marker, node.axes);
            node.health = null;
            this._syncLabel(node);
        });
        this._ensureLinkCapacity(this.nodes.size);
        this._attachRobotModel();
        this.setSelected(this.selectedId);
        this.worldDirty = true;
        this.linkColorsDirty = true;
    }

    _applyTransforms() {
        let changed = this.worldDirty;
        this.nodes.forEach((node) => {
            const entry = this.store.get(node.id);
            if (!entry || entry.rev === node.rev) {
                return;
            }
            node.rev = entry.rev;
            _pos.set(entry.t[0], entry.t[1], entry.t[2]);
            _quat.set(entry.q[0], entry.q[1], entry.q[2], entry.q[3]);
            if (_quat.lengthSq() < 1e-12) {
                _quat.identity();
            } else {
                _quat.normalize();
            }
            node.group.matrix.compose(_pos, _quat, _one);
            changed = true;
        });
        if (!changed) {
            return;
        }
        this.worldDirty = false;

        this.tfRoot.matrix.identity();
        this.tfRoot.updateMatrixWorld(true);
        const fixed = this.nodes.get(this.fixedFrameId);
        if (fixed) {
            _mat.copy(fixed.group.matrixWorld).invert();
            this.tfRoot.matrix.copy(_mat);
            this.tfRoot.updateMatrixWorld(true);
        }
        this._updateLinkPositions();
        this.needsRender = true;
    }

    _updateHealth() {
        const now = performance.now();
        this.nodes.forEach((node) => {
            const health = this.store.health(this.store.get(node.id), now);
            if (health !== node.health) {
                node.health = health;
                node.marker.material = this.healthMaterials[health];
                if (node.label) {
                    node.label.element.dataset.health = health;
                }
                this.linkColorsDirty = true;
                this.needsRender = true;
            }
        });
        if (this.linkColorsDirty) {
            this.linkColorsDirty = false;
            this._updateLinkColors();
        }
    }

    _linkedNodes() {
        const result = [];
        this.nodes.forEach((node) => {
            const parentGroup = node.group.parent;
            if (parentGroup && parentGroup !== this.tfRoot && parentGroup.userData.frameId) {
                result.push([parentGroup, node]);
            }
        });
        return result;
    }

    _ensureLinkCapacity(count) {
        if (count <= this.linkCapacity) {
            return;
        }
        this.linkCapacity = Math.max(16, count * 2);
        const geometry = new THREE.BufferGeometry();
        const positions = new THREE.BufferAttribute(new Float32Array(this.linkCapacity * 6), 3);
        const colors = new THREE.BufferAttribute(new Float32Array(this.linkCapacity * 6), 3);
        positions.setUsage(THREE.DynamicDrawUsage);
        colors.setUsage(THREE.DynamicDrawUsage);
        geometry.setAttribute('position', positions);
        geometry.setAttribute('color', colors);
        this.links.geometry.dispose();
        this.links.geometry = geometry;
    }

    _updateLinkPositions() {
        const attr = this.links.geometry.getAttribute('position');
        if (!attr) {
            return;
        }
        const array = attr.array;
        const pairs = this._linkedNodes();
        pairs.forEach(([parentGroup, node], i) => {
            _a.setFromMatrixPosition(parentGroup.matrixWorld);
            _b.setFromMatrixPosition(node.group.matrixWorld);
            array.set([_a.x, _a.y, _a.z, _b.x, _b.y, _b.z], i * 6);
        });
        this.links.geometry.setDrawRange(0, pairs.length * 2);
        attr.needsUpdate = true;
    }

    _updateLinkColors() {
        const attr = this.links.geometry.getAttribute('color');
        if (!attr) {
            return;
        }
        const array = attr.array;
        this._linkedNodes().forEach(([, node], i) => {
            _color.setHex(HEALTH_COLORS[node.health] ?? HEALTH_COLORS[HEALTH.OK]).multiplyScalar(LINK_DIM);
            array.set([_color.r, _color.g, _color.b, _color.r, _color.g, _color.b], i * 6);
        });
        attr.needsUpdate = true;
    }

    _applyNodeScale(node) {
        const s = this.axisScale;
        node.axes.scale.setScalar(s);
        node.axes.updateMatrix();
        const selected = node.id === this.selectedId;
        node.marker.scale.setScalar(s * (selected ? 1.4 : 1));
        node.marker.updateMatrix();
        if (selected) {
            this.halo.scale.setScalar(s * 2.4);
            this.halo.updateMatrix();
        }
    }

    _syncLabel(node) {
        const selected = node.id === this.selectedId;
        const visible = this.showLabels || selected;
        if (!node.label && !visible) {
            return;
        }
        if (!node.label) {
            const element = document.createElement('div');
            element.className = 'tf-label';
            element.textContent = node.id;
            element.addEventListener('click', () => this.onPick(node.id));
            node.label = new CSS2DObject(element);
            node.label.center.set(-0.08, 1.15);
            node.group.add(node.label);
        }
        node.label.visible = visible;
        node.label.element.classList.toggle('is-selected', selected);
        if (node.health) {
            node.label.element.dataset.health = node.health;
        }
    }

    _attachRobotModel() {
        this.partGroups.forEach((group) => {
            const node = this.nodes.get(group.userData.frame);
            if (node) {
                node.group.add(group);
            } else {
                group.removeFromParent();
            }
        });
        if (!this.robotGroup) {
            return;
        }
        const baseNode = this.nodes.get('base_link');
        (baseNode ? baseNode.group : this.tfRoot).add(this.robotGroup);

        if (!this.moduleGroup) {
            return;
        }
        const mountNode = this.nodes.get('rmodus_mount');
        if (mountNode) {
            this.moduleGroup.position.set(0, 0, 0);
            this.moduleGroup.rotation.set(0, 0, 0);
            mountNode.group.add(this.moduleGroup);
            return;
        }
        const module = this.robotModel.rmodus_module;
        const offset = module.offset || [0, 0, 0];
        const rpy = module.rpy || [0, 0, 0];
        this.moduleGroup.position.set(offset[0], offset[1], offset[2]);
        this.moduleGroup.rotation.set(rpy[0], rpy[1], rpy[2], 'ZYX');
        this.robotGroup.parent.add(this.moduleGroup);
    }

    /* ---------- camera / view ---------- */

    _applyCameraMode() {
        const is2d = this.mode === '2d';
        this.activeCamera = is2d ? this.orthoCamera : this.perspCamera;
        this.activeControls = is2d ? this.orthoControls : this.perspControls;
        this.perspControls.enabled = !is2d;
        this.orthoControls.enabled = is2d;
        this.container.dataset.cameraMode = this.mode;
        this.needsRender = true;
    }

    _resize() {
        const width = Math.max(1, this.container.clientWidth);
        const height = Math.max(1, this.container.clientHeight);
        const aspect = width / height;
        this.renderer.setSize(width, height, false);
        this.labelRenderer.setSize(width, height);

        this.perspCamera.aspect = aspect;
        this.perspCamera.updateProjectionMatrix();

        const halfH = ORTHO_HALF_HEIGHT;
        this.orthoCamera.left = -halfH * aspect;
        this.orthoCamera.right = halfH * aspect;
        this.orthoCamera.top = halfH;
        this.orthoCamera.bottom = -halfH;
        this.orthoCamera.updateProjectionMatrix();
        this.needsRender = true;
    }

    _pickAt(clientX, clientY) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.pointer.set(
            ((clientX - rect.left) / rect.width) * 2 - 1,
            -((clientY - rect.top) / rect.height) * 2 + 1,
        );
        this.raycaster.setFromCamera(this.pointer, this.activeCamera);
        const hits = this.raycaster.intersectObjects(this.pickTargets, false);
        return hits.length > 0 ? hits[0].object.userData.frameId : null;
    }
}

export function createTfScene(container, store, options) {
    return new TfScene(container, store, options);
}

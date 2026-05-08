(() => {
    const MIN_ZOOM = 0.5;
    const MAX_ZOOM = 8.0;

    function normalizeAngle(angle) {
        while (angle > Math.PI) angle -= Math.PI * 2;
        while (angle < -Math.PI) angle += Math.PI * 2;
        return angle;
    }

    function resolveFrames(frames, rootFrame) {
        const frameMap = new Map();
        frames.forEach((frame) => frameMap.set(frame.child_frame_id, frame));

        const resolved = [{ id: rootFrame, label: rootFrame, x: 0, y: 0, yaw: 0, depth: 0 }];

        function expand(parentId, parentPose, depth) {
            frames
                .filter((frame) => frame.parent_frame_id === parentId)
                .forEach((frame) => {
                    const cosYaw = Math.cos(parentPose.yaw);
                    const sinYaw = Math.sin(parentPose.yaw);
                    const x = parentPose.x + cosYaw * frame.x - sinYaw * frame.y;
                    const y = parentPose.y + sinYaw * frame.x + cosYaw * frame.y;
                    const yaw = normalizeAngle(parentPose.yaw + frame.yaw);
                    const pose = {
                        id: frame.child_frame_id,
                        label: frame.child_frame_id,
                        parentId,
                        x,
                        y,
                        yaw,
                        depth,
                    };
                    resolved.push(pose);
                    expand(frame.child_frame_id, pose, depth + 1);
                });
        }

        expand(rootFrame, { x: 0, y: 0, yaw: 0 }, 1);
        return resolved;
    }

    function createRobotView(canvas) {
        const ctx = canvas.getContext('2d');
        const state = {
            rootFrame: 'base_link',
            frames: [],
            selectedFrameId: null,
            showLabels: false,
            zoom: 2.0,
        };

        function normalizeFrameId(frameId) {
            if (!frameId) {
                return null;
            }
            return String(frameId).replace(/^\/+/, '');
        }

        function drawGrid() {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
            ctx.lineWidth = 1;
            const step = 32;
            for (let x = 0; x <= canvas.width; x += step) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, canvas.height);
                ctx.stroke();
            }
            for (let y = 0; y <= canvas.height; y += step) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }
        }

        function projectPoint(centerX, centerY, scale, worldX, worldY) {
            return {
                x: centerX - worldY * scale,
                y: centerY - worldX * scale,
            };
        }

        function drawAxes(centerX, centerY) {
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(centerX, 20);
            ctx.lineTo(centerX, canvas.height - 20);
            ctx.moveTo(20, centerY);
            ctx.lineTo(canvas.width - 20, centerY);
            ctx.stroke();
        }

        function computeScale(poses) {
            if (poses.length <= 1) return 110;
            const maxExtent = poses.reduce((acc, pose) => {
                return Math.max(acc, Math.abs(pose.x), Math.abs(pose.y));
            }, 0.25);
            const base = Math.min(140, Math.max(55, (Math.min(canvas.width, canvas.height) * 0.36) / maxExtent));
            return base * state.zoom;
        }

        function drawFrameAxes(x, y, yaw, highlighted = false) {
            const axisLength = highlighted ? 28 : 20;
            const xDx = -Math.sin(yaw) * axisLength;
            const xDy = -Math.cos(yaw) * axisLength;
            const yDx = -Math.cos(yaw) * axisLength;
            const yDy = Math.sin(yaw) * axisLength;

            ctx.lineWidth = highlighted ? 3 : 2;
            ctx.strokeStyle = '#ef4444';
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(x + xDx, y + xDy);
            ctx.stroke();

            ctx.strokeStyle = '#22c55e';
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(x + yDx, y + yDy);
            ctx.stroke();

            ctx.fillStyle = '#3b82f6';
            ctx.beginPath();
            ctx.arc(x, y, highlighted ? 5 : 3.5, 0, Math.PI * 2);
            ctx.fill();
        }

        function drawRobot(centerX, centerY) {
            drawFrameAxes(centerX, centerY, 0, true);
        }

        function drawFrameLabel(x, y, text, highlighted) {
            ctx.fillStyle = highlighted ? '#111' : 'rgba(11, 14, 20, 0.85)';
            const padding = 4;
            const width = ctx.measureText(text).width + padding * 2;
            const height = 16;
            ctx.beginPath();
            ctx.roundRect(x + 6, y - 22, width, height, 6);
            ctx.fill();
            ctx.fillStyle = highlighted ? '#00d4ff' : '#cbd5e1';
            ctx.fillText(text, x + 10, y - 11);
        }

        function drawFrames(poses, centerX, centerY, scale) {
            poses.forEach((pose) => {
                if (pose.id === state.rootFrame) {
                    return;
                }

                const projected = projectPoint(centerX, centerY, scale, pose.x, pose.y);
                const x = projected.x;
                const y = projected.y;
                const highlighted = pose.id === state.selectedFrameId;

                ctx.save();
                drawFrameAxes(x, y, pose.yaw, highlighted);
                ctx.restore();

                if (state.showLabels) {
                    drawFrameLabel(x, y, pose.label, highlighted);
                }
            });
        }

        function drawLegend() {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '12px Inter, system-ui, sans-serif';
            ctx.fillText('Top view, base frame at center', 20, canvas.height - 18);
            ctx.fillStyle = '#ef4444';
            ctx.fillText('X', canvas.width - 72, canvas.height - 18);
            ctx.fillStyle = '#22c55e';
            ctx.fillText('Y', canvas.width - 54, canvas.height - 18);
            ctx.fillStyle = '#3b82f6';
            ctx.fillText('Z', canvas.width - 36, canvas.height - 18);
        }

        return {
            setFrames(frames, rootFrame) {
                state.frames = Array.isArray(frames) ? frames : [];
                state.rootFrame = normalizeFrameId(rootFrame) || state.rootFrame;
                this.draw();
            },
            setSelectedFrame(frameId) {
                state.selectedFrameId = normalizeFrameId(frameId);
                this.draw();
            },
            setShowLabels(show) {
                state.showLabels = Boolean(show);
                this.draw();
            },
            setZoom(zoomValue) {
                const zoom = Number.isFinite(zoomValue) ? zoomValue : state.zoom;
                state.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
                this.draw();
            },
            draw() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#05080d';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.font = '10px Inter, system-ui, sans-serif';
                drawGrid();

                const centerX = canvas.width / 2;
                const centerY = canvas.height / 2;
                drawAxes(centerX, centerY);

                const poses = resolveFrames(state.frames, state.rootFrame);
                const scale = computeScale(poses);
                drawRobot(centerX, centerY);
                drawFrames(poses, centerX, centerY, scale);
                drawLegend();
            },
        };
    }

    window.createRobotView = createRobotView;
})();

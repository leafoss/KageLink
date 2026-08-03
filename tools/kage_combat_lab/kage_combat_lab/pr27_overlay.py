from __future__ import annotations

from pathlib import Path
import os

import cv2
import numpy as np

from .pr27_native_grid import LocalBackgroundState, PR27FrameResult, SpriteClass, TrackState


class PR27DebugOverlay:
    """PR27.6 local-only overlay. No global grid or global changed-cell authority."""

    def __init__(self, *, window_name: str = "Kage Combat Lab - PR27.6 Local ROI") -> None:
        self.window_name = window_name
        self.created = False

    @staticmethod
    def _track_color(category: SpriteClass, state: TrackState) -> tuple[int,int,int]:
        if state is TrackState.TEMPORARILY_MISSING:
            return (150,150,150)
        if category is SpriteClass.PLAYER:
            return (255,180,0)
        if category is SpriteClass.ENEMY:
            return (0,0,255)
        if category is SpriteClass.NPC:
            return (255,0,255)
        return (0,255,255)

    @staticmethod
    def _background_color(state: LocalBackgroundState | None) -> tuple[int,int,int]:
        if state is LocalBackgroundState.OCCLUDED_BY_EFFECT:
            return (0,100,255)
        if state in {LocalBackgroundState.UNKNOWN, LocalBackgroundState.LEARNING_BACKGROUND}:
            return (0,220,220)
        return (70,70,70)

    def render(self, result: PR27FrameResult) -> np.ndarray:
        canvas = result.arena_bgr.copy()
        target_id = None if result.target is None else result.target.track_id
        enemy_cell = result.enemy_relative_cell

        for cell in result.cells:
            key = (cell.row,cell.column)
            if key == (0,0):
                color,thickness = (255,180,0),4
            elif key == enemy_cell:
                color,thickness = (0,0,255),4
            else:
                color,thickness = self._background_color(result.local_background_states.get(key)),1
            cv2.rectangle(canvas,(cell.x,cell.y),(cell.x+cell.width-1,cell.y+cell.height-1),color,thickness)
            label = "PLAYER CELL (0,0)" if key == (0,0) else f"({cell.row:+d},{cell.column:+d})"
            if key == enemy_cell:
                label = f"ENEMY CELL ({cell.row:+d},{cell.column:+d})"
            cv2.putText(canvas,label,(cell.x+2,cell.y+13),cv2.FONT_HERSHEY_SIMPLEX,0.34,color,1,cv2.LINE_AA)

        if result.roi_center is not None:
            cx,cy = int(round(result.roi_center[0])),int(round(result.roi_center[1]))
            cv2.circle(canvas,(cx,cy),result.roi_radius_cells*64,(255,150,0),1,cv2.LINE_AA)

        for track in result.tracks:
            if track.track_state is TrackState.LOST or track.body_bbox is None:
                continue
            color = self._track_color(track.classification,track.track_state)
            bx,by,bw,bh = track.body_bbox
            thickness = 4 if track.track_id == target_id else 2
            cv2.rectangle(canvas,(bx,by),(bx+bw,by+bh),color,thickness)
            if track.classification is SpriteClass.PLAYER:
                label = f"PLAYER BODY containment={result.player_body_containment_ratio:.2f}"
            elif track.track_id == target_id:
                label = f"LOCKED ENEMY ID{track.track_id}"
            else:
                label = f"BODY ID{track.track_id} {track.classification.value}"
            cv2.putText(canvas,label,(bx,max(16,by-5)),cv2.FONT_HERSHEY_SIMPLEX,0.40,color,1,cv2.LINE_AA)
            if track.body_anchor is not None:
                ax,ay = int(round(track.body_anchor[0])),int(round(track.body_anchor[1]))
                cv2.drawMarker(canvas,(ax,ay),color,cv2.MARKER_CROSS,14,2)
                cv2.putText(canvas,f"A{track.anchor_cell}",(ax+5,ay+14),cv2.FONT_HERSHEY_SIMPLEX,0.34,color,1,cv2.LINE_AA)

        status1 = (
            f"frame={result.frame_index} state={result.state.value} local={result.local_state.value} "
            f"action={result.action.value} ROI_RADIUS={result.roi_radius_cells} ROI_CELLS={result.roi_processed_cell_count}"
        )
        control_enabled = os.environ.get("KAGE_PR27_CONTROL_MODE", "").strip().upper() == "CONTROL_ENABLED"
        status2 = (
            f"PLAYER_CELL=(0,0) ENEMY_CELL={enemy_cell if enemy_cell is not None else '-'} "
            f"R_LATCHED={str(control_enabled).lower()} FACING={result.facing_detected or 'UNKNOWN'} "
            f"CONFIRMED={str(result.facing_confirmed).lower()}"
        )
        cv2.rectangle(canvas,(0,0),(min(canvas.shape[1]-1,1400),42),(0,0,0),-1)
        cv2.putText(canvas,status1,(6,16),cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,255),1,cv2.LINE_AA)
        cv2.putText(canvas,status2,(6,34),cv2.FONT_HERSHEY_SIMPLEX,0.42,(255,255,255),1,cv2.LINE_AA)
        return canvas

    def show(self,image:np.ndarray)->bool:
        if not self.created:
            cv2.namedWindow(self.window_name,cv2.WINDOW_NORMAL)
            self.created=True
        cv2.imshow(self.window_name,image)
        key=cv2.waitKey(1)&0xFF
        return key not in (27,ord('q'))

    @staticmethod
    def save(image:np.ndarray,path:Path)->None:
        path.parent.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(path),image)

    @staticmethod
    def close()->None:
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass

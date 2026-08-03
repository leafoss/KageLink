from __future__ import annotations

import math
from typing import Sequence

from .pr27_fragments import DescriptorFactory
from .pr27_model import CELL_SIZE_PX, PR27Config, SpriteClass, SpriteObservation, TrackState, TrackedSprite
from .pr27_registry import KnownSpriteRegistry


class SpriteTracker:
    def __init__(self, config: PR27Config, registry: KnownSpriteRegistry | None = None) -> None:
        self.config = config.normalized()
        self.registry = registry or KnownSpriteRegistry()
        self.tracks: dict[int,TrackedSprite] = {}
        self.next_track_id = 1
        self.player_track_id: int|None = None
        self.enemy_track_id: int|None = None
        self.pending_enemy_track_id: int|None = None
        self.pending_enemy_hits = 0
        self.trainer_exclusion_bbox: tuple[int,int,int,int]|None = None
        self.trainer_forbidden_cells: frozenset[tuple[int,int]] = frozenset()
        self.last_candidate_rejections: list[str] = []

    def set_trainer_exclusion(self,bbox:tuple[int,int,int,int]|None,forbidden_cells:Sequence[tuple[int,int]]=())->None:
        self.trainer_exclusion_bbox=bbox
        self.trainer_forbidden_cells=frozenset(forbidden_cells)

    @staticmethod
    def _bbox_iou(a,b)->float:
        ax,ay,aw,ah=a; bx,by,bw,bh=b
        left,top=max(ax,bx),max(ay,by); right,bottom=min(ax+aw,bx+bw),min(ay+ah,by+bh)
        intersection=max(0,right-left)*max(0,bottom-top)
        return intersection/max(1,aw*ah+bw*bh-intersection)

    @staticmethod
    def _bbox_intersects(a,b)->bool:
        ax,ay,aw,ah=a; bx,by,bw,bh=b
        return not (ax+aw<=bx or bx+bw<=ax or ay+ah<=by or by+bh<=ay)

    @staticmethod
    def _anchor_cell_distance(left,right)->int:
        if left is None or right is None: return 999
        return max(abs(left[0]-right[0]),abs(left[1]-right[1]))

    @staticmethod
    def _predicted_anchor(track:TrackedSprite)->tuple[float,float]:
        if len(track.movement_history)<2: return track.center
        previous,current=track.movement_history[-2],track.movement_history[-1]
        return current[0]+(current[0]-previous[0]),current[1]+(current[1]-previous[1])

    def _inside_roi(self,key:tuple[int,int]|None)->bool:
        return key is not None and key[0]*key[0]+key[1]*key[1] <= self.config.roi_radius_cells**2

    def _trainer_rejection_observation(self,observation:SpriteObservation)->str|None:
        if not observation.has_body_lock: return "BODY_LOCK_MISSING"
        if not self._inside_roi(observation.anchor_cell): return "OUTSIDE_LOCAL_ROI"
        if observation.anchor_cell in self.trainer_forbidden_cells: return "TRAINER_FORBIDDEN_ANCHOR_CELL"
        if self.trainer_exclusion_bbox is not None:
            if observation.body_bbox is not None and self._bbox_intersects(observation.body_bbox,self.trainer_exclusion_bbox): return "TRAINER_BODY_BBOX_INTERSECTION"
            if observation.body_anchor is not None:
                x,y,w,h=self.trainer_exclusion_bbox; ax,ay=observation.body_anchor
                if x<=ax<x+w and y<=ay<y+h: return "TRAINER_BODY_ANCHOR_INSIDE_ZONE"
        return None

    def _trainer_rejection_track(self,track:TrackedSprite)->str|None:
        if not track.has_body_lock: return "BODY_LOCK_MISSING"
        if not self._inside_roi(track.anchor_cell): return "OUTSIDE_LOCAL_ROI"
        if track.anchor_cell in self.trainer_forbidden_cells: return "TRAINER_FORBIDDEN_ANCHOR_CELL"
        if self.trainer_exclusion_bbox is not None:
            if track.body_bbox is not None and self._bbox_intersects(track.body_bbox,self.trainer_exclusion_bbox): return "TRAINER_BODY_BBOX_INTERSECTION"
            if track.body_anchor is not None:
                x,y,w,h=self.trainer_exclusion_bbox; ax,ay=track.body_anchor
                if x<=ax<x+w and y<=ay<y+h: return "TRAINER_BODY_ANCHOR_INSIDE_ZONE"
        return None

    def _association_score(self,track:TrackedSprite,observation:SpriteObservation,*,target_track:bool,arena_shape:Sequence[int])->float:
        del arena_shape
        if not track.has_body_lock or not observation.has_body_lock: return 0.0
        trainer_reason=self._trainer_rejection_observation(observation)
        if trainer_reason is not None and (target_track or track.classification is SpriteClass.ENEMY): return 0.0
        cell_distance=self._anchor_cell_distance(track.anchor_cell,observation.anchor_cell)
        allowed_step=(1+track.missing_frames) if target_track else self.config.maximum_track_cell_step+track.missing_frames
        if cell_distance>allowed_step: return 0.0
        appearance=DescriptorFactory.similarity(track.appearance_signature,observation.descriptor)
        old_bbox,new_bbox=track.body_bbox,observation.body_bbox
        assert old_bbox is not None and new_bbox is not None and observation.body_anchor is not None
        old_area,new_area=max(1,old_bbox[2]*old_bbox[3]),max(1,new_bbox[2]*new_bbox[3])
        size=min(old_area,new_area)/max(old_area,new_area)
        predicted=self._predicted_anchor(track)
        anchor_distance=math.hypot(observation.body_anchor[0]-predicted[0],observation.body_anchor[1]-predicted[1])
        max_distance=CELL_SIZE_PX*max(1.25,allowed_step+0.75)
        if target_track and anchor_distance>max_distance: return 0.0
        proximity=max(0.0,1.0-anchor_distance/max_distance)
        overlap=self._bbox_iou(old_bbox,new_bbox)
        temporal=max(0.0,1.0-cell_distance/max(1.0,allowed_step+1.0))
        body=min(track.body_confidence,observation.body_confidence)
        if target_track and (appearance<self.config.target_minimum_appearance or size<0.52 or body<self.config.body_lock_min_confidence): return 0.0
        score=0.40*appearance+0.28*proximity+0.14*overlap+0.08*size+0.06*temporal+0.04*body
        return min(1.0,score+0.05) if target_track else score

    def _update_track(self,track:TrackedSprite,observation:SpriteObservation,frame_index:int,score:float)->None:
        track.previous_cells=track.current_cells; track.current_cells=observation.cells
        track.fragments=observation.fragments; track.native_bbox=observation.native_bbox
        track.combined_mask=observation.combined_mask; track.appearance_signature=observation.descriptor
        track.body_bbox=observation.body_bbox; track.body_anchor=observation.body_anchor
        track.anchor_cell=observation.anchor_cell; track.body_confidence=observation.body_confidence
        track.last_seen_frame=frame_index; track.missing_frames=0; track.observations+=1
        track.confidence=max(track.confidence*0.60,score); track.track_state=TrackState.TRACKED
        track.rejection_reason=self._trainer_rejection_track(track)
        if track.body_anchor is not None: track.movement_history.append(track.body_anchor)

    def _create_track(self,observation:SpriteObservation,frame_index:int)->TrackedSprite|None:
        rejection=self._trainer_rejection_observation(observation)
        if rejection is not None:
            self.last_candidate_rejections.append(f"observation={observation.observation_id}:{rejection}"); return None
        track=TrackedSprite(
            track_id=self.next_track_id,current_cells=observation.cells,previous_cells=frozenset(),fragments=observation.fragments,
            native_bbox=observation.native_bbox,combined_mask=observation.combined_mask,appearance_signature=observation.descriptor,
            first_seen_frame=frame_index,last_seen_frame=frame_index,body_bbox=observation.body_bbox,
            body_anchor=observation.body_anchor,anchor_cell=observation.anchor_cell,body_confidence=observation.body_confidence,
            confidence=max(0.50,observation.body_confidence),
        )
        if track.body_anchor is not None: track.movement_history.append(track.body_anchor)
        self.tracks[track.track_id]=track; self.next_track_id+=1
        return track

    def _player_anchor(self,arena_shape:Sequence[int])->tuple[float,float]:
        if self.player_track_id is not None:
            player=self.tracks.get(self.player_track_id)
            if player is not None and player.body_anchor is not None: return player.body_anchor
        h,w=int(arena_shape[0]),int(arena_shape[1])
        return w*self.config.player_anchor_x_ratio,h*self.config.player_anchor_y_ratio

    def _classify_known_or_player(self,track:TrackedSprite,arena_shape:Sequence[int])->None:
        trainer_reason=self._trainer_rejection_track(track)
        if trainer_reason is not None:
            track.classification=SpriteClass.NPC; track.known_enemy=False; track.rejection_reason=trainer_reason
            if self.enemy_track_id==track.track_id: self.enemy_track_id=None
            return
        known,score=self.registry.best_match(track.appearance_signature)
        if known is not None and score>=self.config.known_sprite_threshold:
            track.classification=known.category; track.known_sprite_id=known.sprite_id
            track.known_enemy=known.category is SpriteClass.ENEMY; track.confidence=max(track.confidence,score)
            if known.category is SpriteClass.ENEMY:
                self.enemy_track_id=track.track_id; self.pending_enemy_track_id=None; self.pending_enemy_hits=0; return
        if not track.has_body_lock: return
        expected=self._player_anchor(arena_shape) if self.player_track_id is not None else (int(arena_shape[1])*self.config.player_anchor_x_ratio,int(arena_shape[0])*self.config.player_anchor_y_ratio)
        assert track.body_anchor is not None
        distance=math.hypot(track.body_anchor[0]-expected[0],track.body_anchor[1]-expected[1])
        if track.observations>=self.config.player_confirm_frames and distance<=self.config.player_anchor_radius_px and (self.player_track_id is None or self.player_track_id==track.track_id):
            track.classification=SpriteClass.PLAYER; track.known_enemy=False; self.player_track_id=track.track_id

    def _enemy_candidate_score(self,track:TrackedSprite,arena_shape:Sequence[int])->float:
        if track.track_state is not TrackState.TRACKED or track.track_id==self.player_track_id or not track.has_body_lock: return 0.0
        if track.classification not in {SpriteClass.UNKNOWN,SpriteClass.ENEMY} or track.observations<self.config.enemy_confirm_frames: return 0.0
        trainer_reason=self._trainer_rejection_track(track)
        if trainer_reason is not None:
            track.rejection_reason=trainer_reason; self.last_candidate_rejections.append(f"track={track.track_id}:{trainer_reason}"); return 0.0
        if track.body_confidence<self.config.body_lock_min_confidence:
            self.last_candidate_rejections.append(f"track={track.track_id}:BODY_CONFIDENCE_LOW"); return 0.0
        player=self._player_anchor(arena_shape); assert track.body_anchor is not None and track.body_bbox is not None
        separation=math.hypot(track.body_anchor[0]-player[0],track.body_anchor[1]-player[1])
        if separation<=max(18.0,self.config.player_anchor_radius_px*0.38):
            self.last_candidate_rejections.append(f"track={track.track_id}:PLAYER_ANCHOR_OVERLAP"); return 0.0
        _,_,width,height=track.body_bbox; area=width*height; aspect=width/max(1.0,float(height))
        persistence=min(1.0,track.observations/max(1.0,self.config.enemy_confirm_frames+2.0))
        shape=max(0.0,1.0-abs(aspect-0.65)/1.30)
        size=1.0 if 180<=area<=6000 else max(0.0,1.0-abs(area-2200.0)/6000.0)
        movement=0.0
        if len(track.movement_history)>=2:
            first,last=track.movement_history[0],track.movement_history[-1]
            movement=min(1.0,math.hypot(last[0]-first[0],last[1]-first[1])/24.0)
        proximity=max(0.0,1.0-max(abs(track.anchor_cell[0]),abs(track.anchor_cell[1]))/(self.config.roi_radius_cells+1.0))
        return 0.31*persistence+0.22*shape+0.14*size+0.11*movement+0.09*track.body_confidence+0.05*min(1.0,track.confidence)+0.08*proximity

    def _select_context_enemy(self,arena_shape:Sequence[int])->None:
        if not self.config.enable_context_enemy: return
        if self.enemy_track_id is not None:
            current=self.tracks.get(self.enemy_track_id)
            if current is not None and current.track_state is not TrackState.LOST and self._trainer_rejection_track(current) is None: return
            self.enemy_track_id=None
        scored=[(self._enemy_candidate_score(t,arena_shape),t) for t in self.tracks.values()]
        scored=[item for item in scored if item[0]>=0.56]
        if not scored:
            self.pending_enemy_track_id=None; self.pending_enemy_hits=0; return
        scored.sort(key=lambda item:(item[0],item[1].observations,item[1].body_confidence,-item[1].track_id),reverse=True)
        score,candidate=scored[0]
        if self.pending_enemy_track_id==candidate.track_id: self.pending_enemy_hits+=1
        else: self.pending_enemy_track_id=candidate.track_id; self.pending_enemy_hits=1
        if self.pending_enemy_hits<2: return
        candidate.classification=SpriteClass.ENEMY; candidate.known_enemy=True; candidate.confidence=max(candidate.confidence,score,0.72)
        self.enemy_track_id=candidate.track_id; self.pending_enemy_track_id=None; self.pending_enemy_hits=0

    def update(self,observations:Sequence[SpriteObservation],*,frame_index:int,arena_shape:Sequence[int])->tuple[TrackedSprite,...]:
        self.last_candidate_rejections.clear(); candidates=[]; active=list(self.tracks.values())
        observations=tuple(o for o in observations if self._inside_roi(o.anchor_cell))
        for track in active:
            target=track.track_id==self.enemy_track_id
            threshold=self.config.target_association_min_score if target else self.config.association_min_score
            for index,observation in enumerate(observations):
                score=self._association_score(track,observation,target_track=target,arena_shape=arena_shape)
                if score>=threshold: candidates.append((1 if target else 0,score,track.track_id,index))
        candidates.sort(reverse=True); used_tracks=set(); used_observations=set()
        for _,score,track_id,index in candidates:
            if track_id in used_tracks or index in used_observations: continue
            self._update_track(self.tracks[track_id],observations[index],frame_index,score)
            used_tracks.add(track_id); used_observations.add(index)
        unmatched=[o for i,o in enumerate(observations) if i not in used_observations]
        unmatched.sort(key=lambda item:(item.body_confidence,item.pixel_count),reverse=True)
        for observation in unmatched:
            if len(self.tracks)>=self.config.maximum_active_tracks: break
            track=self._create_track(observation,frame_index)
            if track is not None: used_tracks.add(track.track_id)
        purge=[]
        for track in active:
            if track.track_id in used_tracks: continue
            track.missing_frames+=1
            limit=self.config.target_missing_grace_frames if track.track_id==self.enemy_track_id else self.config.maximum_missing_frames
            if track.missing_frames<=limit: track.track_state=TrackState.TEMPORARILY_MISSING
            else: track.track_state=TrackState.LOST; purge.append(track.track_id)
        for track_id in purge:
            if self.player_track_id==track_id: self.player_track_id=None
            if self.enemy_track_id==track_id: self.enemy_track_id=None
            if self.pending_enemy_track_id==track_id: self.pending_enemy_track_id=None; self.pending_enemy_hits=0
            self.tracks.pop(track_id,None)
        for track in self.tracks.values():
            if track.track_state is TrackState.TRACKED: self._classify_known_or_player(track,arena_shape)
        self._select_context_enemy(arena_shape)
        return tuple(sorted(self.tracks.values(),key=lambda item:item.track_id))

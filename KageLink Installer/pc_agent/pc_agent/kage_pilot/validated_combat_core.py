from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

CARDINALS={"UP","DOWN","LEFT","RIGHT"}
ENGAGE_HOSTILITY=0.38
ATTACK_HOSTILITY=0.68


def direction_from_grid(dx: int|None, dy: int|None) -> str:
    if dx is None and dy is None:return "-"
    x=int(dx or 0);y=int(dy or 0)
    if x==0 and y==0:return "-"
    if abs(x)>=abs(y) and x!=0:return "RIGHT" if x>0 else "LEFT"
    return "DOWN" if y>0 else "UP"


def cheb(dx:int|None,dy:int|None)->Optional[int]:
    if dx is None and dy is None:return None
    return max(abs(int(dx or 0)),abs(int(dy or 0)))


def clamp01(v:float)->float:return max(0.0,min(1.0,float(v)))


def hostility_score(*, materialization_causality:float=0.0, network_fusion:float=0.0,
                    spawn_motion_match:float=0.0, approach:float=0.0,
                    damage_evidence:float=0.0, hostile_action:float=0.0)->float:
    """Generic evidence accumulator. No entity is hostile because of its name/template.

    Dojo supplies materialization causality. Forest can supply approach/damage/action evidence.
    The weights intentionally allow a strong causal spawn + motion match to attack even when
    the network decoder is temporarily unavailable, while network alone cannot attack.
    """
    return clamp01(
        0.54*clamp01(materialization_causality)
        +0.26*clamp01(network_fusion)
        +0.22*clamp01(spawn_motion_match)
        +0.18*clamp01(approach)
        +0.54*clamp01(damage_evidence)
        +0.42*clamp01(hostile_action)
    )


def hostile_state(score:float)->str:
    s=float(score)
    if s>=ATTACK_HOSTILITY:return "ATTACK"
    if s>=ENGAGE_HOSTILITY:return "ENGAGE"
    return "UNKNOWN"


@dataclass(slots=True)
class VisualEvidence:
    timestamp: float
    dx: int
    dy: int
    track_id: int|None=None
    confidence: float=0.0
    body_valid: bool=True
    source: str="VISUAL"
    combatant_verified: bool=False
    noncombatant: bool=False  # retained for compatibility; V3.2 does not infer safety from preexistence
    appearance_score: float|None=None
    binding_reason: str=""
    entity_id: str|None=None
    identity_confidence: float=0.0
    hostility: float=0.0
    network_fused: bool=False
    def direction(self):return direction_from_grid(self.dx,self.dy)
    def distance(self):return cheb(self.dx,self.dy)


@dataclass(slots=True)
class ProtocolEvidence:
    timestamp: float
    dx: int|None=None
    dy: int|None=None
    x_trusted: bool=False
    y_trusted: bool=False
    prefix9: str|None=None
    confidence: float=0.0
    source: str="PROTOCOL"
    def direction(self):return direction_from_grid(self.dx if self.x_trusted else None,self.dy if self.y_trusted else None)


@dataclass(slots=True)
class FusedGeometry:
    timestamp: float
    dx: int|None
    dy: int|None
    confidence: float
    source: str
    visual_fresh: bool
    protocol_fresh: bool
    conflict: bool=False
    track_id: int|None=None
    combatant_verified: bool=False
    entity_id: str|None=None
    hostility: float=0.0
    identity_confidence: float=0.0
    def direction(self):return direction_from_grid(self.dx,self.dy)
    def distance(self):return cheb(self.dx,self.dy)
    def in_cardinal_line(self)->bool:
        if self.dx is None or self.dy is None:return False
        return (self.dx==0) ^ (self.dy==0)


@dataclass(slots=True)
class V3Decision:
    state:str
    hold_r:bool
    navigation:str="HOLD"
    face:str="-"
    h_request:bool=False
    geometry:FusedGeometry|None=None
    reason:str=""


@dataclass(slots=True)
class HCommand:
    generation:int
    wall:float
    mono:float
    confirmed:bool=False
    protocol_ts:float|None=None


@dataclass(slots=True)
class CombatV3State:
    state:str="WAIT_WORLD"
    materialization_at:float|None=None
    network_prefix9:str|None=None
    network_at:float|None=None
    network_confidence:float=0.0
    engaged:bool=False
    victory:bool=False
    last_visual:VisualEvidence|None=None
    visual_history:deque=field(default_factory=lambda:deque(maxlen=12))
    last_protocol:ProtocolEvidence|None=None
    last_fused:FusedGeometry|None=None
    visual_lock:bool=False
    visual_hits:int=0
    target_entity_id:str|None=None
    target_hostility:float=0.0
    target_identity_confidence:float=0.0
    facing:str|None=None
    facing_at:float=-1e9
    face_pending:str|None=None
    last_move_at:float=-1e9
    last_protocol_move_stamp:float=-1e9
    pursuit_steps:int=0
    h_generation:int=0
    h_commands:deque=field(default_factory=lambda:deque(maxlen=12))
    h_last_sent:float=-1e9
    h_last_confirmed:float=-1e9
    h_effect_until:float=-1e9
    runtime_at:float|None=None
    first_lock_at:float|None=None
    first_move_at:float|None=None
    first_h_at:float|None=None
    victory_at:float|None=None
    r_physical_at:float|None=None
    input_generation:int=0
    input_kind:str|None=None
    input_key:str|None=None
    input_until:float=-1e9
    input_consumed:bool=True
    # HF1 Mobility Fix: one-frame navigation compensation only.
    # It never creates identity, geometry authority or H authority.
    near_move_direction:str|None=None
    near_move_visual_ts:float=-1e9
    near_move_pre_dx:int|None=None
    near_move_pre_dy:int|None=None
    near_move_entity_id:str|None=None
    suppress_repeat_visual_ts:float=-1e9
    suppress_repeat_direction:str|None=None

    def reset(self,runtime_at:float|None=None):
        fresh=CombatV3State(runtime_at=runtime_at)
        for k in self.__dataclass_fields__:setattr(self,k,getattr(fresh,k))

    def on_materialization(self,ts:float):
        runtime=self.runtime_at
        self.reset(runtime)
        self.materialization_at=float(ts);self.engaged=True;self.state="ENGAGED"

    def on_network(self,prefix:str,ts:float,confidence:float):
        self.network_prefix9=prefix;self.network_at=float(ts);self.network_confidence=float(confidence);self.engaged=True
        if self.state=="WAIT_WORLD":self.state="ENGAGED"

    def on_identity(self,entity_id:str,ts:float,identity_confidence:float,hostility:float):
        """Bind logical identity without inventing current geometry."""
        self.target_entity_id=str(entity_id)
        self.target_identity_confidence=max(self.target_identity_confidence,float(identity_confidence))
        self.target_hostility=max(self.target_hostility,float(hostility))
        self.engaged=True
        if self.state=="WAIT_WORLD":self.state="ENGAGED"

    def on_visual(self,e:VisualEvidence):
        # V3.2 Dojo Final receives only the current round-bound logical opponent here.
        # Identity is established by the round binder; geometry/hostility cannot mint it.
        if not e.body_valid or not e.combatant_verified or e.noncombatant:
            return
        # Mobility-only compensation. A single 40 ms pulse from distance 2 should
        # normally close one tile. If the first NEW visual sample after that pulse
        # repeats the exact same round-body geometry, treat only that sample as a
        # likely camera/self-motion lag for navigation. The following fresh visual
        # always releases the suppression, even when the target is truly co-moving.
        if self.near_move_direction and float(e.timestamp)>self.near_move_visual_ts+1e-6:
            same_entity=(self.near_move_entity_id is None or e.entity_id==self.near_move_entity_id)
            same_geometry=(self.near_move_pre_dx is not None and self.near_move_pre_dy is not None and int(e.dx)==int(self.near_move_pre_dx) and int(e.dy)==int(self.near_move_pre_dy))
            if same_entity and same_geometry:
                self.suppress_repeat_visual_ts=float(e.timestamp)
                self.suppress_repeat_direction=self.near_move_direction
            self.near_move_direction=None
            self.near_move_visual_ts=-1e9
            self.near_move_pre_dx=None
            self.near_move_pre_dy=None
            self.near_move_entity_id=None
        elif self.suppress_repeat_visual_ts>-1e8 and float(e.timestamp)>self.suppress_repeat_visual_ts+1e-6:
            self.suppress_repeat_visual_ts=-1e9
            self.suppress_repeat_direction=None
        self.last_visual=e;self.visual_history.append(e)
        self.target_entity_id=e.entity_id or (f"track:{e.track_id}" if e.track_id is not None else None)
        self.target_hostility=float(e.hostility);self.target_identity_confidence=float(e.identity_confidence)
        strong=e.confidence>=0.48 and e.identity_confidence>=0.50
        if strong:
            self.visual_hits+=1
            if not self.visual_lock:
                self.visual_lock=True;self.first_lock_at=self.first_lock_at or e.timestamp
        if self.visual_lock:self.state="TRACKING"

    def on_protocol(self,e:ProtocolEvidence):self.last_protocol=e

    def fuse(self,now:float)->FusedGeometry|None:
        v=self.last_visual;p=self.last_protocol
        vf=bool(v and now-v.timestamp<=0.85 and v.body_valid and v.combatant_verified and not v.noncombatant and v.entity_id==self.target_entity_id)
        pf=bool(p and now-p.timestamp<=0.70 and (p.x_trusted or p.y_trusted) and (self.network_prefix9 is None or p.prefix9==self.network_prefix9))
        if not vf and not pf:return None
        if vf and pf:
            # The successful V3.0 fight was visually driven.  A fresh body already bound to
            # the logical round opponent is therefore the spatial authority.  Protocol bytes
            # reinforce confidence and become fallback during visual loss, but must not pull
            # a valid body toward a stale/partially calibrated coordinate.
            diffs=[]
            if p.x_trusted and p.dx is not None:diffs.append(abs(int(v.dx)-int(p.dx)))
            if p.y_trusted and p.dy is not None:diffs.append(abs(int(v.dy)-int(p.dy)))
            disagree=bool(diffs and max(diffs)>1)
            dx=int(v.dx);dy=int(v.dy)
            if disagree:
                conf=max(.58,min(.92,.56+.28*v.confidence+.08*v.identity_confidence))
                source="VISUAL_PROTOCOL_DISAGREE"
            else:
                conf=min(.99,.58+.22*v.confidence+.10*p.confidence+.08*v.identity_confidence)
                source="VISUAL+BYTE_AGREE"
            g=FusedGeometry(now,dx,dy,conf,source,True,True,False,v.track_id,True,v.entity_id,v.hostility,v.identity_confidence)
        elif vf:
            g=FusedGeometry(now,int(v.dx),int(v.dy),max(0.55,v.confidence),v.source,True,False,False,v.track_id,True,v.entity_id,v.hostility,v.identity_confidence)
        else:
            # Network/byte-only data may sustain one tile after a real hostile visual lock,
            # but can never create a target or authorize H on its own.
            if not self.visual_lock or p is None or self.target_entity_id is None:return None
            dx=int(p.dx) if p.x_trusted and p.dx is not None else (self.last_fused.dx if self.last_fused else None)
            dy=int(p.dy) if p.y_trusted and p.dy is not None else (self.last_fused.dy if self.last_fused else None)
            if dx is None and dy is None:return None
            g=FusedGeometry(now,dx,dy,min(0.82,p.confidence),"BYTE_CONTINUITY",False,True,False,None,False,self.target_entity_id,self.target_hostility,self.target_identity_confidence)
        self.last_fused=g
        return g

    def decide(self,now_wall:float,now_mono:float)->V3Decision:
        if self.victory:return V3Decision("VICTORY",False,reason="authoritative victory")
        if not self.engaged:return V3Decision("WAIT_WORLD",False,reason="waiting materialization/hostile engagement")
        g=self.fuse(now_wall)
        if g is None:
            why="waiting round-born opponent identity"
            if self.network_prefix9:why="network entity alive; waiting current round body"
            return V3Decision("ENGAGED",True,reason=why)
        if g.conflict:return V3Decision("SENSOR_CONFLICT",True,geometry=g,reason="byte/visual geometry conflict")
        d=g.distance();direction=g.direction()
        if d is None or direction not in CARDINALS:return V3Decision("TRACKING",True,geometry=g,reason="geometry incomplete")
        if now_mono<self.h_effect_until or now_mono-self.h_last_sent<1.10:
            return V3Decision("H_EFFECT",True,geometry=g,reason="H causal/effect hold")
        if d<=1 and g.in_cardinal_line():
            current_visual=bool(g.visual_fresh and g.combatant_verified and self.last_visual and now_wall-self.last_visual.timestamp<=0.70 and self.last_visual.entity_id==self.target_entity_id and not self.last_visual.noncombatant)
            attack_authority=bool(current_visual and g.identity_confidence>=0.55)
            can_h=(attack_authority and now_mono-self.h_last_sent>=1.45 and now_mono-self.h_last_confirmed>=1.25 and g.confidence>=0.56)
            reason="round-bound opponent in cardinal line" if attack_authority else "cardinal geometry without current round-bound visual body"
            return V3Decision("MELEE",True,face=direction,h_request=can_h,geometry=g,reason=reason)
        if d<=1:
            return V3Decision("ALIGN",True,navigation=f"MOVE_{direction}",face=direction,geometry=g,reason="hostile entity adjacent but diagonal")
        if g.source=="BYTE_CONTINUITY" and self.last_protocol is not None and self.last_protocol.timestamp<=self.last_protocol_move_stamp+1e-6:
            return V3Decision("TRACKING",True,geometry=g,reason="byte continuity already consumed this protocol update")
        # Surgical mobility fix: do not repeat the same near-target pulse from the
        # first unchanged visual sample after our own movement. This is HOLD for
        # exactly one visual observation, only at raw distance 2, and has no effect
        # on R, identity, reacquire, H or victory.
        if (d==2 and g.visual_fresh and self.last_visual is not None and
            self.suppress_repeat_visual_ts>-1e8 and
            abs(float(self.last_visual.timestamp)-self.suppress_repeat_visual_ts)<=1e-6 and
            direction==self.suppress_repeat_direction):
            return V3Decision("TRACKING",True,geometry=g,reason="mobility compensation: skip one repeated near-target visual after self movement")
        return V3Decision("CHASE",True,navigation=f"MOVE_{direction}",face=direction,geometry=g,reason="round-bound opponent farther than melee")

    def mark_r_physical(self,now_wall:float):
        if self.r_physical_at is None:self.r_physical_at=float(now_wall)

    def mark_move(self,now_wall:float,now_mono:float,protocol_stamp:float|None=None):
        self.pursuit_steps+=1;self.last_move_at=now_mono
        if protocol_stamp is not None:self.last_protocol_move_stamp=max(self.last_protocol_move_stamp,float(protocol_stamp))
        # Record only a distance-2 visual pursuit. No new gate/state machine is
        # introduced; this merely allows the next visual sample to suppress one
        # duplicate navigation pulse if the camera has not reflected SELF movement.
        g=self.last_fused;v=self.last_visual
        if g is not None and v is not None and g.visual_fresh and g.distance()==2 and g.direction() in CARDINALS:
            self.near_move_direction=g.direction()
            self.near_move_visual_ts=float(v.timestamp)
            self.near_move_pre_dx=int(v.dx);self.near_move_pre_dy=int(v.dy)
            self.near_move_entity_id=v.entity_id
        else:
            self.near_move_direction=None
            self.near_move_visual_ts=-1e9
            self.near_move_pre_dx=None;self.near_move_pre_dy=None;self.near_move_entity_id=None
        self.first_move_at=self.first_move_at or now_wall

    def register_h(self,now_wall:float,now_mono:float)->HCommand:
        self.h_generation+=1;c=HCommand(self.h_generation,now_wall,now_mono);self.h_commands.append(c);self.h_last_sent=now_mono;self.first_h_at=self.first_h_at or now_wall;return c

    def confirm_h(self,protocol_ts:float,arrival_mono:float)->HCommand|None:
        candidates=[c for c in self.h_commands if not c.confirmed and -0.05<=protocol_ts-c.wall<=1.10]
        if not candidates:return None
        c=max(candidates,key=lambda x:x.wall);c.confirmed=True;c.protocol_ts=protocol_ts;self.h_last_confirmed=arrival_mono;self.h_effect_until=arrival_mono+1.55;return c

    def authorize_input(self,kind:str,key:str,now_mono:float,ttl:float=.28)->int:
        self.input_generation+=1;self.input_kind=str(kind).upper();self.input_key=str(key).lower();self.input_until=float(now_mono)+float(ttl);self.input_consumed=False
        return self.input_generation

    def input_allowed(self,kind:str,key:str,now_mono:float,consume:bool=False)->bool:
        ok=(not self.input_consumed and self.input_kind==str(kind).upper() and self.input_key==str(key).lower() and float(now_mono)<=self.input_until)
        if ok and consume:self.input_consumed=True
        return bool(ok)

    def clear_input_authority(self):
        self.input_consumed=True;self.input_kind=None;self.input_key=None;self.input_until=-1e9

    def on_victory(self,now_wall:float):
        self.victory=True;self.engaged=False;self.state="VICTORY";self.victory_at=now_wall;self.clear_input_authority()

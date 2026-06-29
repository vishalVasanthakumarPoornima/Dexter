from __future__ import annotations

from backend.jobs.models import Approval, ApplicationPacket, utc_now


def ensure_approval(session, packet: ApplicationPacket) -> Approval:
    approval = (
        session.query(Approval)
        .filter(Approval.application_packet_id == packet.id)
        .order_by(Approval.id.desc())
        .first()
    )
    if approval is None:
        approval = Approval(application_packet_id=packet.id, status="requested")
        session.add(approval)
        session.flush()
    return approval


def approve_packet(session, packet_id: int, notes: str = "") -> Approval:
    packet = session.get(ApplicationPacket, packet_id)
    if packet is None:
        raise ValueError(f"Unknown packet id: {packet_id}")
    approval = ensure_approval(session, packet)
    approval.status = "approved"
    approval.approved_at = utc_now()
    approval.notes = notes
    session.flush()
    return approval


def reject_packet(session, packet_id: int, notes: str = "") -> Approval:
    packet = session.get(ApplicationPacket, packet_id)
    if packet is None:
        raise ValueError(f"Unknown packet id: {packet_id}")
    approval = ensure_approval(session, packet)
    approval.status = "rejected"
    approval.rejected_at = utc_now()
    approval.notes = notes
    session.flush()
    return approval

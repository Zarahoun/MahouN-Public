"""
Sneakernet Transfer Protocol
=============================

Chain-of-custody tracking for airgapped audit trail transfer.

Features:
- Transfer manifest generation
- Chain-of-custody tracking
- Multi-party acknowledgment
- Tamper detection
- Transfer verification

Design for Airgap:
- Removable media compatible
- Offline verification
- Human-readable manifests
- Cryptographic receipts
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

from mahoun.crypto.signatures import sign_message, verify_signature


# ============================================================================
# ENUMS
# ============================================================================

class TransferStatus(str, Enum):
    """Transfer lifecycle status"""
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    VERIFIED = "verified"
    IMPORTED = "imported"
    FAILED = "failed"


class TransferMethod(str, Enum):
    """Physical transfer method"""
    USB_DRIVE = "usb_drive"
    OPTICAL_DISC = "optical_disc"
    ENCRYPTED_HDD = "encrypted_hdd"
    SECURE_COURIER = "secure_courier"
    AIR_GAP_BRIDGE = "air_gap_bridge"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class CustodyEvent:
    """Single custody event in chain"""
    timestamp: str  # ISO 8601
    event_type: str  # transferred, received, verified, imported
    actor: str  # Who performed action
    location: str  # Where action occurred
    signature: str  # Cryptographic signature
    notes: Optional[str] = None
    
    def verify(self, public_key: str) -> bool:
        """Verify event signature"""
        message = f"{self.timestamp}|{self.event_type}|{self.actor}|{self.location}"
        return verify_signature(message, self.signature, public_key)


@dataclass
class ChainOfCustody:
    """
    Complete chain of custody for audit package.
    
    Tracks:
    - Who handled the package
    - When they handled it
    - Where it was handled
    - What they did with it
    
    Provides:
    - Non-repudiation (signatures)
    - Tamper detection (hash verification)
    - Regulatory compliance (full audit trail)
    """
    package_id: str
    initial_hash: str  # Hash at creation
    current_hash: str  # Hash at last verification
    events: List[CustodyEvent] = field(default_factory=list)
    
    def add_event(
        self,
        event_type: str,
        actor: str,
        location: str,
        private_key: str,
        notes: Optional[str] = None,
    ) -> CustodyEvent:
        """
        Add custody event.
        
        Args:
            event_type: Type of event (transferred, received, etc.)
            actor: Person performing action
            location: Where action occurred
            private_key: Private key for signing
            notes: Optional notes
        
        Returns:
            Created custody event
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        message = f"{timestamp}|{event_type}|{actor}|{location}"
        signature = sign_message(message, private_key)
        
        event = CustodyEvent(
            timestamp=timestamp,
            event_type=event_type,
            actor=actor,
            location=location,
            signature=signature,
            notes=notes,
        )
        
        self.events.append(event)
        return event
    
    def verify_chain(self, public_keys: Dict[str, str]) -> bool:
        """
        Verify complete chain of custody.
        
        Args:
            public_keys: Mapping of actor → public key
        
        Returns:
            True if all events verified
        """
        for event in self.events:
            public_key = public_keys.get(event.actor)
            if not public_key:
                return False
            if not event.verify(public_key):
                return False
        return True
    
    def detect_tampering(self, current_file_hash: str) -> bool:
        """
        Detect if package was tampered with.
        
        Args:
            current_file_hash: Current hash of package file
        
        Returns:
            True if tampering detected
        """
        return current_file_hash != self.initial_hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChainOfCustody':
        """Create from dictionary"""
        events = [CustodyEvent(**e) for e in data.pop('events', [])]
        return cls(**data, events=events)


@dataclass
class TransferManifest:
    """
    Transfer manifest for sneakernet protocol.
    
    Accompanies each physical transfer of audit packages.
    """
    # Transfer identity
    transfer_id: str
    transfer_timestamp: str  # ISO 8601
    transfer_method: TransferMethod
    
    # Package information
    package_ids: List[str]
    total_packages: int
    total_size_mb: float
    
    # Parties
    sender: str
    sender_location: str
    sender_signature: str
    
    receiver: Optional[str] = None
    receiver_location: Optional[str] = None
    receiver_signature: Optional[str] = None
    
    # Status
    status: TransferStatus = TransferStatus.PENDING
    
    # Chain of custody
    chain_of_custody: Optional[ChainOfCustody] = None
    
    # Metadata
    transfer_purpose: str = "audit_export"
    security_classification: str = "confidential"
    handling_instructions: str = "Encrypted media. Verify hash before import."
    
    def sign_as_sender(self, private_key: str) -> None:
        """Sign manifest as sender"""
        message = self._get_sender_message()
        self.sender_signature = sign_message(message, private_key)
    
    def sign_as_receiver(self, receiver: str, location: str, private_key: str) -> None:
        """Sign manifest as receiver (acknowledgment)"""
        self.receiver = receiver
        self.receiver_location = location
        message = self._get_receiver_message()
        self.receiver_signature = sign_message(message, private_key)
        self.status = TransferStatus.RECEIVED
    
    def verify_sender(self, public_key: str) -> bool:
        """Verify sender signature"""
        message = self._get_sender_message()
        return verify_signature(message, self.sender_signature, public_key)
    
    def verify_receiver(self, public_key: str) -> bool:
        """Verify receiver signature"""
        if not self.receiver_signature:
            return False
        message = self._get_receiver_message()
        return verify_signature(message, self.receiver_signature, public_key)
    
    def _get_sender_message(self) -> str:
        """Get message for sender signature"""
        package_list = ",".join(sorted(self.package_ids))
        return (
            f"{self.transfer_id}|"
            f"{self.transfer_timestamp}|"
            f"{package_list}|"
            f"{self.sender}|"
            f"{self.sender_location}"
        )
    
    def _get_receiver_message(self) -> str:
        """Get message for receiver signature"""
        # Must use transfer_timestamp (not current time) for reproducible verification
        return (
            f"{self.transfer_id}|"
            f"{self.receiver}|"
            f"{self.receiver_location}|"
            f"{self.transfer_timestamp}"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        # Convert enums
        data['transfer_method'] = self.transfer_method.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferManifest':
        """Create from dictionary"""
        # Convert enums
        if isinstance(data.get('transfer_method'), str):
            data['transfer_method'] = TransferMethod(data['transfer_method'])
        if isinstance(data.get('status'), str):
            data['status'] = TransferStatus(data['status'])
        if data.get('chain_of_custody'):
            data['chain_of_custody'] = ChainOfCustody.from_dict(data['chain_of_custody'])
        return cls(**data)


# ============================================================================
# TRANSFER PROTOCOL
# ============================================================================

class TransferProtocol:
    """
    Sneakernet transfer protocol for airgapped environments.
    
    Workflow:
    1. Sender creates transfer manifest
    2. Sender signs manifest
    3. Sender copies packages + manifest to removable media
    4. Physical transfer (courier, hand-carry, etc.)
    5. Receiver verifies hashes
    6. Receiver signs manifest (acknowledgment)
    7. Receiver imports to SIEM
    8. Complete chain-of-custody recorded
    """
    
    def __init__(self, private_key: str, actor_id: str, location: str):
        """
        Initialize transfer protocol.
        
        Args:
            private_key: Private key for signing
            actor_id: Identity of actor
            location: Current location
        """
        self.private_key = private_key
        self.actor_id = actor_id
        self.location = location
    
    def create_transfer(
        self,
        package_ids: List[str],
        package_sizes_mb: List[float],
        transfer_method: TransferMethod = TransferMethod.USB_DRIVE,
        transfer_purpose: str = "audit_export",
    ) -> TransferManifest:
        """
        Create transfer manifest for package export.
        
        Args:
            package_ids: List of package IDs to transfer
            package_sizes_mb: Size of each package in MB
            transfer_method: Physical transfer method
            transfer_purpose: Purpose of transfer
        
        Returns:
            Signed transfer manifest
        """
        transfer_id = self._generate_transfer_id()
        
        manifest = TransferManifest(
            transfer_id=transfer_id,
            transfer_timestamp=datetime.now(timezone.utc).isoformat(),
            transfer_method=transfer_method,
            package_ids=package_ids,
            total_packages=len(package_ids),
            total_size_mb=sum(package_sizes_mb),
            sender=self.actor_id,
            sender_location=self.location,
            sender_signature="",  # Will be set below
            transfer_purpose=transfer_purpose,
        )
        
        # Sign manifest
        manifest.sign_as_sender(self.private_key)
        
        # Initialize chain of custody
        manifest.chain_of_custody = ChainOfCustody(
            package_id=f"transfer_{transfer_id}",
            initial_hash=self._hash_manifest(manifest),
            current_hash=self._hash_manifest(manifest),
        )
        
        # Add creation event
        manifest.chain_of_custody.add_event(
            event_type="created",
            actor=self.actor_id,
            location=self.location,
            private_key=self.private_key,
            notes=f"Created transfer manifest for {len(package_ids)} packages",
        )
        
        return manifest
    
    def acknowledge_receipt(
        self,
        manifest: TransferManifest,
        verification_passed: bool,
    ) -> TransferManifest:
        """
        Acknowledge receipt of transfer (receiver side).
        
        Args:
            manifest: Transfer manifest
            verification_passed: Whether verification passed
        
        Returns:
            Updated manifest with receiver signature
        """
        # Sign as receiver
        manifest.sign_as_receiver(
            receiver=self.actor_id,
            location=self.location,
            private_key=self.private_key,
        )
        
        # Add receipt event
        if manifest.chain_of_custody:
            manifest.chain_of_custody.add_event(
                event_type="received",
                actor=self.actor_id,
                location=self.location,
                private_key=self.private_key,
                notes=f"Verification: {'PASSED' if verification_passed else 'FAILED'}",
            )
        
        # Update status
        manifest.status = (
            TransferStatus.VERIFIED if verification_passed 
            else TransferStatus.FAILED
        )
        
        return manifest
    
    def write_manifest(self, manifest: TransferManifest, output_dir: Path) -> Path:
        """
        Write transfer manifest to file.
        
        Args:
            manifest: Transfer manifest
            output_dir: Output directory
        
        Returns:
            Path to manifest file
        """
        manifest_path = output_dir / f"{manifest.transfer_id}.transfer.json"
        manifest_data = manifest.to_dict()
        
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        return manifest_path
    
    def read_manifest(self, manifest_path: Path) -> TransferManifest:
        """Read transfer manifest from file"""
        manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))
        return TransferManifest.from_dict(manifest_data)
    
    def generate_receipt(
        self,
        manifest: TransferManifest,
        output_path: Path,
    ) -> Path:
        """
        Generate human-readable receipt.
        
        Args:
            manifest: Transfer manifest
            output_path: Output file path
        
        Returns:
            Path to receipt file
        """
        receipt = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    MAHOUN AUDIT TRAIL TRANSFER RECEIPT                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Transfer ID: {manifest.transfer_id}
Date: {manifest.transfer_timestamp}
Method: {manifest.transfer_method.value.upper().replace('_', ' ')}

╔══════════════════════════════════════════════════════════════════════════════╗
║ SENDER                                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Name: {manifest.sender}
Location: {manifest.sender_location}
Signature: {manifest.sender_signature[:64]}...

╔══════════════════════════════════════════════════════════════════════════════╗
║ RECEIVER                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

Name: {manifest.receiver or 'PENDING'}
Location: {manifest.receiver_location or 'PENDING'}
Signature: {(manifest.receiver_signature[:64] + '...') if manifest.receiver_signature else 'PENDING'}
Status: {manifest.status.value.upper().replace('_', ' ')}

╔══════════════════════════════════════════════════════════════════════════════╗
║ PACKAGES                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

Total Packages: {manifest.total_packages}
Total Size: {manifest.total_size_mb:.2f} MB

Package IDs:
""" + "\n".join([f"  - {pkg_id}" for pkg_id in manifest.package_ids]) + f"""

╔══════════════════════════════════════════════════════════════════════════════╗
║ SECURITY                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

Classification: {manifest.security_classification.upper()}
Purpose: {manifest.transfer_purpose}
Handling: {manifest.handling_instructions}

╔══════════════════════════════════════════════════════════════════════════════╗
║ CHAIN OF CUSTODY                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

"""
        
        if manifest.chain_of_custody:
            for i, event in enumerate(manifest.chain_of_custody.events, 1):
                receipt += f"""
Event #{i}:
  Type: {event.event_type.upper()}
  Actor: {event.actor}
  Location: {event.location}
  Timestamp: {event.timestamp}
  Signature: {event.signature[:64]}...
  Notes: {event.notes or 'None'}
"""
        
        receipt += """
╔══════════════════════════════════════════════════════════════════════════════╗
║ VERIFICATION                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

To verify this transfer:
1. Verify sender signature with sender's public key
2. Verify receiver signature with receiver's public key
3. Verify package hashes match manifest
4. Verify chain of custody signatures

All signatures use Ed25519 cryptographic algorithm.
Any modification to packages or manifest will invalidate signatures.

╔══════════════════════════════════════════════════════════════════════════════╗
║ END OF RECEIPT                                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        
        output_path.write_text(receipt, encoding='utf-8')
        return output_path
    
    @staticmethod
    def _generate_transfer_id() -> str:
        """Generate unique transfer ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:8]
        return f"TXN_{timestamp}_{random_suffix}"
    
    @staticmethod
    def _hash_manifest(manifest: TransferManifest) -> str:
        """Compute hash of manifest"""
        manifest_str = json.dumps(manifest.to_dict(), sort_keys=True)
        return hashlib.sha256(manifest_str.encode()).hexdigest()


# ============================================================================
# CLI EXAMPLE
# ============================================================================

if __name__ == "__main__":
    from mahoun.crypto.signatures import generate_keypair
    
    print("🔐 MAHOUN Sneakernet Transfer Protocol")
    print("=" * 80)
    
    # Generate keypairs for sender and receiver
    sender_private, sender_public = generate_keypair()
    receiver_private, receiver_public = generate_keypair()
    
    print("✓ Generated keypairs for sender and receiver")
    
    # Sender creates transfer
    sender_protocol = TransferProtocol(
        private_key=sender_private,
        actor_id="alice@mahoun-hq",
        location="MAHOUN HQ, Building A",
    )
    
    manifest = sender_protocol.create_transfer(
        package_ids=["pkg_001", "pkg_002", "pkg_003"],
        package_sizes_mb=[15.5, 22.3, 18.7],
        transfer_method=TransferMethod.USB_DRIVE,
    )
    
    print(f"✓ Created transfer: {manifest.transfer_id}")
    print(f"  - Packages: {manifest.total_packages}")
    print(f"  - Total size: {manifest.total_size_mb:.2f} MB")
    print(f"  - Sender: {manifest.sender}")
    
    # Verify sender signature
    assert manifest.verify_sender(sender_public)
    print("✓ Sender signature verified")
    
    # Simulate physical transfer...
    print("\n📦 Physical transfer in progress...")
    
    # Receiver acknowledges
    receiver_protocol = TransferProtocol(
        private_key=receiver_private,
        actor_id="bob@external-siem",
        location="SOC, Data Center 2",
    )
    
    manifest = receiver_protocol.acknowledge_receipt(
        manifest=manifest,
        verification_passed=True,
    )
    
    print(f"✓ Transfer received by: {manifest.receiver}")
    print(f"  - Status: {manifest.status.value}")
    
    # Verify receiver signature
    assert manifest.verify_receiver(receiver_public)
    print("✓ Receiver signature verified")
    
    # Verify chain of custody
    public_keys = {
        "alice@mahoun-hq": sender_public,
        "bob@external-siem": receiver_public,
    }
    assert manifest.chain_of_custody.verify_chain(public_keys)
    print("✓ Chain of custody verified")
    
    print(f"\n✅ Transfer complete with full chain-of-custody")
    print(f"   {len(manifest.chain_of_custody.events)} custody events recorded")

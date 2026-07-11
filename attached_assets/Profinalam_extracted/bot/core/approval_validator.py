"""
Approval Validator - Comprehensive approval validation and filtering
Validates approvals for:
- Unlimited vs Limited access
- Expiration status
- Current validity
- Usability status
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
from web3 import Web3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AccessType(Enum):
    """Type of access granted by approval"""
    UNLIMITED = "unlimited"  # uint256.max or very large amount
    LIMITED = "limited"      # specific amount
    ZERO = "zero"           # no access


class ValidityStatus(Enum):
    """Current validity status of approval"""
    VALID = "valid"                    # Currently usable
    EXPIRED = "expired"                # Time-based expiration passed
    REVOKED = "revoked"                # Allowance set to zero
    INSUFFICIENT = "insufficient"      # Balance insufficient for execution
    UNKNOWN = "unknown"                # Cannot determine validity


class ApprovalHealthStatus(Enum):
    """Overall health status of approval"""
    HEALTHY = "healthy"                # All checks passed
    WARNING = "warning"                # Some issues detected
    CRITICAL = "critical"              # Major issues
    UNUSABLE = "unusable"              # Cannot be used


@dataclass
class ApprovalValidation:
    """Complete validation result for an approval"""
    # Identifiers
    owner: str
    spender: str
    token_address: str
    token_symbol: str
    
    # Access information
    access_type: AccessType
    allowance_amount: int
    allowance_decimal: float  # Formatted with decimals
    
    # Expiration information
    has_expiration: bool
    expiration_timestamp: Optional[int] = None
    expiration_date: Optional[str] = None
    days_until_expiration: Optional[float] = None
    
    # Validity checks
    validity_status: ValidityStatus = ValidityStatus.VALID
    is_currently_valid: bool = True
    
    # Additional checks
    current_balance: float = 0.0
    can_execute: bool = False
    
    # Health status
    health_status: ApprovalHealthStatus = ApprovalHealthStatus.HEALTHY
    
    # Validation issues
    issues: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/display"""
        return {
            "owner": self.owner,
            "spender": self.spender,
            "token": self.token_symbol,
            "access_type": self.access_type.value,
            "allowance": {
                "amount": self.allowance_amount,
                "formatted": f"{self.allowance_decimal:.6f}",
                "type": self.access_type.value
            },
            "expiration": {
                "has_expiration": self.has_expiration,
                "timestamp": self.expiration_timestamp,
                "date": self.expiration_date,
                "days_remaining": self.days_until_expiration
            },
            "validity": {
                "status": self.validity_status.value,
                "is_valid": self.is_currently_valid,
                "can_execute": self.can_execute
            },
            "balance": self.current_balance,
            "health": {
                "status": self.health_status.value,
                "issues": self.issues,
                "warnings": self.warnings
            }
        }


class ApprovalValidator:
    """Comprehensive approval validator"""
    
    # Constants for validation
    UNLIMITED_THRESHOLD = 2**255  # uint256.max / 2 (very large number)
    ZERO_ADDRESS = "0x" + "0" * 40
    
    def __init__(self, web3_provider: Web3):
        self.w3 = web3_provider
    
    def validate_approval(
        self,
        owner: str,
        spender: str,
        token_address: str,
        token_symbol: str,
        allowance_amount: int,
        decimals: int,
        current_balance: float = 0.0,
        expiration_timestamp: Optional[int] = None,
        allow_expired: bool = False
    ) -> ApprovalValidation:
        """
        Comprehensively validate an approval
        
        Args:
            owner: Token owner address
            spender: Spender address
            token_address: Token contract address
            token_symbol: Token symbol (USDT, USDC, etc)
            allowance_amount: Current allowance in smallest unit
            decimals: Token decimals
            current_balance: Owner's current token balance
            expiration_timestamp: Unix timestamp of expiration (if any)
            allow_expired: Whether to allow expired approvals
            
        Returns:
            ApprovalValidation object with complete validation results
        """
        validation = ApprovalValidation(
            owner=owner,
            spender=spender,
            token_address=token_address,
            token_symbol=token_symbol,
            access_type=AccessType.ZERO,
            allowance_amount=allowance_amount,
            allowance_decimal=allowance_amount / (10 ** decimals)
        )
        
        # Check 1: Determine access type
        self._check_access_type(validation, allowance_amount)
        
        # Check 2: Validate spender address
        self._validate_addresses(validation)
        
        # Check 3: Check expiration status
        if expiration_timestamp:
            self._check_expiration(validation, expiration_timestamp, allow_expired)
        
        # Check 4: Determine overall validity
        self._determine_validity(validation)
        
        # Check 5: Check if can execute
        self._check_execution_feasibility(validation, current_balance, allowance_amount)
        
        # Check 6: Determine health status
        self._determine_health_status(validation)
        
        return validation
    
    def _check_access_type(self, validation: ApprovalValidation, allowance: int):
        """Determine if approval grants unlimited or limited access"""
        if allowance == 0:
            validation.access_type = AccessType.ZERO
            validation.issues.append("❌ Allowance is zero - no access granted")
        elif allowance >= self.UNLIMITED_THRESHOLD:
            validation.access_type = AccessType.UNLIMITED
            validation.warnings.append("⚠️ Unlimited approval - spender can drain entire balance")
        else:
            validation.access_type = AccessType.LIMITED
    
    def _validate_addresses(self, validation: ApprovalValidation):
        """Validate owner and spender addresses"""
        owner_lower = validation.owner.lower()
        spender_lower = validation.spender.lower()
        
        # Check for zero address
        if spender_lower == self.ZERO_ADDRESS:
            validation.issues.append("❌ Spender is zero address - invalid")
            validation.is_currently_valid = False
        
        if owner_lower == self.ZERO_ADDRESS:
            validation.issues.append("❌ Owner is zero address - invalid")
            validation.is_currently_valid = False
        
        # Check for self-approval
        if owner_lower == spender_lower:
            validation.warnings.append("⚠️ Owner and spender are the same")
    
    def _check_expiration(
        self,
        validation: ApprovalValidation,
        expiration_timestamp: int,
        allow_expired: bool = False
    ):
        """Check if approval has expiration and if it's still valid"""
        validation.has_expiration = True
        validation.expiration_timestamp = expiration_timestamp
        
        # Convert timestamp to datetime
        expiration_date = datetime.fromtimestamp(expiration_timestamp)
        validation.expiration_date = expiration_date.isoformat()
        
        # Calculate days until expiration
        now = datetime.now()
        days_remaining = (expiration_date - now).total_seconds() / 86400
        validation.days_until_expiration = days_remaining
        
        if days_remaining < 0:
            # Expired
            validation.validity_status = ValidityStatus.EXPIRED
            validation.is_currently_valid = not allow_expired
            validation.issues.append(
                f"❌ Approval expired {abs(days_remaining):.1f} days ago"
            )
        elif days_remaining < 1:
            # Expires soon
            validation.warnings.append(
                f"⚠️ Approval expires in {days_remaining:.2f} hours"
            )
        elif days_remaining < 7:
            # Expires within a week
            validation.warnings.append(
                f"⚠️ Approval expires in {days_remaining:.1f} days"
            )
    
    def _determine_validity(self, validation: ApprovalValidation):
        """Determine overall validity status"""
        if not validation.is_currently_valid:
            return
        
        if validation.access_type == AccessType.ZERO:
            validation.validity_status = ValidityStatus.REVOKED
            validation.is_currently_valid = False
        elif validation.validity_status == ValidityStatus.EXPIRED:
            validation.is_currently_valid = False
        else:
            validation.validity_status = ValidityStatus.VALID
    
    def _check_execution_feasibility(
        self,
        validation: ApprovalValidation,
        current_balance: float,
        allowance: int
    ):
        """Check if approval can be actually executed"""
        validation.current_balance = current_balance
        
        # If not valid, cannot execute
        if not validation.is_currently_valid:
            validation.can_execute = False
            return
        
        # If zero access, cannot execute
        if validation.access_type == AccessType.ZERO:
            validation.can_execute = False
            validation.issues.append("❌ Cannot execute - allowance is zero")
            return
        
        # If balance is zero, cannot execute
        if current_balance <= 0:
            validation.can_execute = False
            validation.issues.append("❌ Cannot execute - owner balance is zero")
            return
        
        # Can execute
        validation.can_execute = True
    
    def _determine_health_status(self, validation: ApprovalValidation):
        """Determine overall health status"""
        if validation.issues:
            validation.health_status = ApprovalHealthStatus.UNUSABLE
        elif validation.validity_status != ValidityStatus.VALID:
            validation.health_status = ApprovalHealthStatus.CRITICAL
        elif validation.warnings:
            validation.health_status = ApprovalHealthStatus.WARNING
        else:
            validation.health_status = ApprovalHealthStatus.HEALTHY
    
    def validate_batch(
        self,
        approvals: List[Dict]
    ) -> Dict[str, ApprovalValidation]:
        """
        Validate multiple approvals at once
        
        Args:
            approvals: List of approval dicts with validation parameters
            
        Returns:
            Dictionary mapping approval keys to validation results
        """
        results = {}
        for approval in approvals:
            key = f"{approval['owner']}_{approval['spender']}_{approval['token']}"
            results[key] = self.validate_approval(
                owner=approval['owner'],
                spender=approval['spender'],
                token_address=approval.get('token_address', approval['token']),
                token_symbol=approval.get('token_symbol', 'UNKNOWN'),
                allowance_amount=approval['allowance'],
                decimals=approval.get('decimals', 18),
                current_balance=approval.get('balance', 0),
                expiration_timestamp=approval.get('expiration'),
                allow_expired=approval.get('allow_expired', False)
            )
        
        return results
    
    def filter_valid_approvals(
        self,
        approvals: List[ApprovalValidation],
        require_unlimited: bool = False,
        require_non_expired: bool = True,
        require_executable: bool = True
    ) -> Tuple[List[ApprovalValidation], List[ApprovalValidation]]:
        """
        Filter approvals based on criteria
        
        Args:
            approvals: List of validation results
            require_unlimited: Only return unlimited approvals
            require_non_expired: Filter out expired approvals
            require_executable: Only return approvals that can be executed
            
        Returns:
            Tuple of (valid_approvals, invalid_approvals)
        """
        valid = []
        invalid = []
        
        for approval in approvals:
            is_valid = True
            
            # Check unlimited requirement
            if require_unlimited and approval.access_type != AccessType.UNLIMITED:
                is_valid = False
            
            # Check expiration requirement
            if require_non_expired and approval.validity_status == ValidityStatus.EXPIRED:
                is_valid = False
            
            # Check executable requirement
            if require_executable and not approval.can_execute:
                is_valid = False
            
            if is_valid and approval.is_currently_valid:
                valid.append(approval)
            else:
                invalid.append(approval)
        
        return valid, invalid
    
    def get_approval_summary(self, validation: ApprovalValidation) -> str:
        """Get human-readable summary of approval validation"""
        summary_lines = [
            f"\n{'='*60}",
            f"🔍 APPROVAL VALIDATION REPORT",
            f"{'='*60}",
            f"Token: {validation.token_symbol}",
            f"Owner: {validation.owner[:6]}...{validation.owner[-4:]}",
            f"Spender: {validation.spender[:6]}...{validation.spender[-4:]}",
            f"",
            f"📊 ACCESS INFORMATION:",
            f"  Type: {validation.access_type.value.upper()}",
            f"  Allowance: {validation.allowance_decimal:.6f} {validation.token_symbol}",
            f"  Raw Amount: {validation.allowance_amount}",
            f"",
            f"⏰ EXPIRATION STATUS:",
        ]
        
        if validation.has_expiration:
            summary_lines.extend([
                f"  Has Expiration: Yes",
                f"  Expires: {validation.expiration_date}",
                f"  Days Remaining: {validation.days_until_expiration:.1f}",
            ])
        else:
            summary_lines.append(f"  Has Expiration: No (permanent)")
        
        summary_lines.extend([
            f"",
            f"✅ VALIDITY CHECK:",
            f"  Status: {validation.validity_status.value.upper()}",
            f"  Currently Valid: {'Yes' if validation.is_currently_valid else 'No'}",
            f"  Can Execute: {'Yes' if validation.can_execute else 'No'}",
            f"  Current Balance: {validation.current_balance:.6f}",
            f"",
            f"🏥 HEALTH STATUS: {validation.health_status.value.upper()}",
        ])
        
        if validation.issues:
            summary_lines.append(f"")
            summary_lines.append(f"❌ ISSUES ({len(validation.issues)}):")
            for issue in validation.issues:
                summary_lines.append(f"  {issue}")
        
        if validation.warnings:
            summary_lines.append(f"")
            summary_lines.append(f"⚠️  WARNINGS ({len(validation.warnings)}):")
            for warning in validation.warnings:
                summary_lines.append(f"  {warning}")
        
        if not validation.issues and not validation.warnings:
            summary_lines.append(f"")
            summary_lines.append(f"✓ No issues detected - approval is healthy!")
        
        summary_lines.append(f"{'='*60}\n")
        
        return "\n".join(summary_lines)


class ApprovalAutoFilter:
    """
    خودکار approval ها را فیلتر و skip کند
    Automatically filters and skips invalid approvals
    
    Skip conditions:
    1. allowance = 0 (no access)
    2. balance = 0 (no funds)
    3. expired (time-based expiration passed)
    """
    
    def __init__(self, log_skips: bool = True):
        self.log_skips = log_skips
        self.skipped_count = 0
        self.skip_reasons = {}  # برای آمار
    
    def should_skip(
        self,
        approval: ApprovalValidation,
        strict_mode: bool = True
    ) -> Tuple[bool, str]:
        """
        بررسی کند آیا این approval باید skip شود
        Check if approval should be skipped
        
        Args:
            approval: ApprovalValidation object
            strict_mode: اگر True، هر warning را skip کند
            
        Returns:
            Tuple[should_skip: bool, reason: str]
        """
        skip_reasons = []
        
        # Check 1: دسترسی نیست (allowance = 0)
        if approval.access_type == AccessType.ZERO:
            skip_reasons.append("❌ دسترسی نیست (allowance = 0)")
        
        # Check 2: پول نیست (balance = 0)
        if approval.current_balance <= 0:
            skip_reasons.append("❌ پول نیست (balance = 0)")
        
        # Check 3: انقضا شده (expired)
        if approval.validity_status == ValidityStatus.EXPIRED:
            skip_reasons.append("❌ انقضا شده (expired)")
        
        # strict mode: هر مسئله دیگری را skip کن
        if strict_mode and approval.issues:
            skip_reasons.append(f"⚠️  مسائل دیگر ({len(approval.issues)})")
        
        should_skip = len(skip_reasons) > 0
        
        if should_skip:
            self.skipped_count += 1
            reason = " | ".join(skip_reasons)
            self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1
            
            if self.log_skips:
                logger.warning(
                    f"⏭️  Skip approval: {approval.token_symbol} "
                    f"({approval.owner[:6]}...{approval.owner[-4:]}) → {reason}"
                )
            
            return True, reason
        
        return False, "✅ معتبر - ادامه دادن"
    
    def filter_approvals(
        self,
        approvals: List[ApprovalValidation],
        strict_mode: bool = True
    ) -> Tuple[List[ApprovalValidation], List[Tuple[ApprovalValidation, str]]]:
        """
        فیلتر و تقسیم approval ها
        Filter and split approvals into valid and skipped
        
        Args:
            approvals: List of ApprovalValidation objects
            strict_mode: اگر True، هر warning را skip کند
            
        Returns:
            Tuple[valid_approvals, skipped_approvals_with_reasons]
        """
        valid = []
        skipped = []
        
        for approval in approvals:
            should_skip, reason = self.should_skip(approval, strict_mode)
            if should_skip:
                skipped.append((approval, reason))
            else:
                valid.append(approval)
        
        return valid, skipped
    
    def get_skip_statistics(self) -> Dict:
        """آمار skip ها را بگیر"""
        return {
            "total_skipped": self.skipped_count,
            "skip_reasons": self.skip_reasons
        }
    
    def reset_statistics(self):
        """آمار را reset کن"""
        self.skipped_count = 0
        self.skip_reasons = {}


# Utility functions for quick validation
def quick_validate(
    allowance: int,
    decimals: int = 18,
    expiration: Optional[int] = None
) -> Dict[str, any]:
    """Quick validation without Web3 dependency"""
    result = {
        "access_type": "unlimited" if allowance >= 2**255 else "limited" if allowance > 0 else "zero",
        "allowance_formatted": allowance / (10 ** decimals),
        "is_expired": False,
        "is_valid": True
    }
    
    if expiration:
        now_ts = int(datetime.now().timestamp())
        result["is_expired"] = now_ts > expiration
        result["is_valid"] = not result["is_expired"]
        result["days_remaining"] = (expiration - now_ts) / 86400
    
    return result

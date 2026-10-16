from datetime import date
import pytest
from app.schemas import BookingRequirements
from app.agent_schemas import StatePatch,DateOperation
from app.state_updates import merge_requirements
from app.tools import BusinessError

def test_relative_extension_preserves_known_fields():
    before=BookingRequirements(destination='Goa',adults=2,check_in=date(2026,11,10),check_out=date(2026,11,12),budget_amount=2000000)
    after=merge_requirements(before,[StatePatch(field='adults',operation='SET',value=4)],[DateOperation(field='check_out',operation='shift_days',days=1)])
    assert after.destination=='Goa' and after.adults==4 and after.check_out==date(2026,11,13)
    assert after.check_in==before.check_in and after.budget_amount==before.budget_amount

def test_duplicate_conflicting_patches_rejected():
    with pytest.raises(BusinessError):merge_requirements(BookingRequirements(),[StatePatch(field='adults',operation='SET',value=2),StatePatch(field='adults',operation='CLEAR')])

def test_relative_dates_require_an_anchor():
    with pytest.raises(BusinessError):merge_requirements(BookingRequirements(),[],[DateOperation(field='check_out',operation='shift_days',days=1)])

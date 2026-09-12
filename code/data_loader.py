import csv
from pathlib import Path
from typing import Dict, Union, Optional
from code.models import Request, FinancialProfile, FinancialEvent, ExchangeRate, PaymentOption, Message, ImageRecord
from code.utils import parse_decimal, parse_date, parse_datetime

def load_requests(path: Union[str, Path]) -> Dict[str, Request]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    requests: Dict[str, Request] = {}
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        # Verify columns exist
        required_columns = {
            'request_id', 'user_id', 'request_date', 'request_type', 
            'requested_amount', 'desired_completion_date', 'allows_partial_payment', 'request_text'
        }
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            rid = row.get('request_id')
            if not rid or rid.strip() == "":
                raise ValueError("Missing or blank request_id")
            
            if rid in requests:
                raise ValueError(f"Duplicate request_id found: {rid}")
            
            # Map values
            try:
                request = Request(
                    request_id=rid,
                    user_id=row['user_id'],
                    request_date=parse_date(row['request_date']),
                    request_type=row['request_type'],
                    requested_amount=parse_decimal(row['requested_amount']),
                    desired_completion_date=parse_date(row['desired_completion_date']),
                    allows_partial_payment=row['allows_partial_payment'].lower() == 'true',
                    request_text=row.get('request_text')
                )
                requests[rid] = request
            except ValueError as e:
                raise ValueError(f"Error parsing request {rid}: {e}")
                
    return requests

def _parse_list(value: str) -> list[str]:
    if not value or value.strip() == "":
        return []
    return [item.strip() for item in value.split('|')]

def load_financial_profiles(path: Union[str, Path]) -> Dict[str, FinancialProfile]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    profiles: Dict[str, FinancialProfile] = {}
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        required_columns = {
            'user_id', 'home_currency', 'current_available_balance', 'minimum_balance_to_keep',
            'financial_priorities', 'expense_categories_to_protect', 
            'expense_categories_user_is_willing_to_reduce', 'expense_categories_user_is_willing_to_stop',
            'payment_methods_user_will_consider', 'max_installment_months'
        }
        
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            uid = row.get('user_id')
            if not uid or uid.strip() == "":
                raise ValueError("Missing or blank user_id")
            
            if uid in profiles:
                raise ValueError(f"Duplicate user_id found: {uid}")
            
            try:
                profiles[uid] = FinancialProfile(
                    user_id=uid,
                    home_currency=row['home_currency'],
                    current_available_balance=parse_decimal(row['current_available_balance']) or 0,
                    minimum_balance_to_keep=parse_decimal(row['minimum_balance_to_keep']) or 0,
                    financial_priorities=_parse_list(row['financial_priorities']),
                    expense_categories_to_protect=_parse_list(row['expense_categories_to_protect']),
                    expense_categories_user_is_willing_to_reduce=_parse_list(row['expense_categories_user_is_willing_to_reduce']),
                    expense_categories_user_is_willing_to_stop=_parse_list(row['expense_categories_user_is_willing_to_stop']),
                    payment_methods_user_will_consider=_parse_list(row['payment_methods_user_will_consider']),
                    max_installment_months=int(row['max_installment_months']) if row.get('max_installment_months') and row['max_installment_months'].strip() else None
                )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Error parsing profile {uid}: {e}")
    
    return profiles

def load_financial_events(path: Union[str, Path]) -> Dict[str, FinancialEvent]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    events: Dict[str, FinancialEvent] = {}
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        required_columns = {
            'event_id', 'user_id', 'event_type', 'description', 'category', 'direction',
            'amount', 'currency', 'event_date', 'settlement_date', 'status', 'linked_event_id',
            'flexibility', 'minimum_allowed_amount'
        }
        
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            eid = row.get('event_id')
            if not eid or eid.strip() == "":
                raise ValueError("Missing or blank event_id")
            
            if eid in events:
                raise ValueError(f"Duplicate event_id found: {eid}")
            
            try:
                events[eid] = FinancialEvent(
                    event_id=eid,
                    user_id=row['user_id'],
                    event_type=row['event_type'],
                    description=row['description'],
                    category=row['category'],
                    direction=row['direction'],
                    amount=parse_decimal(row['amount']),
                    currency=row['currency'],
                    event_date=parse_date(row['event_date']),
                    settlement_date=parse_date(row['settlement_date']),
                    status=row['status'],
                    linked_event_id=row['linked_event_id'] if row.get('linked_event_id') else None,
                    flexibility=row['flexibility'],
                    minimum_allowed_amount=parse_decimal(row['minimum_allowed_amount'])
                )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Error parsing event {eid}: {e}")
    
    return events
def load_exchange_rates(path: Union[str, Path]) -> list[ExchangeRate]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    rates: list[ExchangeRate] = []
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        required_columns = {'rate_date', 'from_currency', 'to_currency', 'rate'}
        
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            try:
                rates.append(ExchangeRate(
                    rate_date=parse_date(row['rate_date']),
                    from_currency=row['from_currency'],
                    to_currency=row['to_currency'],
                    rate=parse_decimal(row['rate'])
                ))
            except (ValueError, TypeError) as e:
                raise ValueError(f"Error parsing exchange rate row {row}: {e}")
    
    return rates

def load_payment_options(path: Union[str, Path]) -> Dict[str, PaymentOption]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    options: Dict[str, PaymentOption] = {}
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        required_columns = {
            'payment_option_id', 'request_id', 'payment_method', 'payment_amount',
            'number_of_payments', 'first_payment_date', 'payment_frequency_days',
            'financing_fee', 'total_payable_amount'
        }
        
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            poid = row.get('payment_option_id')
            if not poid or poid.strip() == "":
                raise ValueError("Missing or blank payment_option_id")
            
            if poid in options:
                raise ValueError(f"Duplicate payment_option_id found: {poid}")
            
            try:
                num_payments = int(row['number_of_payments']) if row.get('number_of_payments') and row['number_of_payments'].strip() else None
                freq_days = int(row['payment_frequency_days']) if row.get('payment_frequency_days') and row['payment_frequency_days'].strip() else None
                
                options[poid] = PaymentOption(
                    payment_option_id=poid,
                    request_id=row['request_id'],
                    payment_method=row['payment_method'],
                    payment_amount=parse_decimal(row['payment_amount']),
                    number_of_payments=num_payments,
                    first_payment_date=parse_date(row['first_payment_date']),
                    payment_frequency_days=freq_days,
                    financing_fee=parse_decimal(row['financing_fee']),
                    total_payable_amount=parse_decimal(row['total_payable_amount'])
                )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Error parsing payment option {poid}: {e}")
    
    return options


def load_messages(path: Union[str, Path]) -> Dict[str, Message]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    messages: Dict[str, Message] = {}
    
    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        
        required_columns = {
            'message_id', 'user_id', 'request_id', 'related_event_id', 'sent_at',
            'source_type', 'message_text'
        }
        
        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            mid = row.get('message_id')
            if not mid or mid.strip() == "":
                raise ValueError("Missing or blank message_id")
            
            if mid in messages:
                raise ValueError(f"Duplicate message_id found: {mid}")
            
            try:
                messages[mid] = Message(
                    message_id=mid,
                    user_id=row['user_id'],
                    request_id=row.get('request_id') if row.get('request_id') and row['request_id'].strip() else None,
                    related_event_id=row.get('related_event_id') if row.get('related_event_id') and row['related_event_id'].strip() else None,
                    sent_at=parse_datetime(row['sent_at']),
                    source_type=row['source_type'],
                    message_text=row['message_text']
                )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Error parsing message {mid}: {e}")
    
    return messages


def load_images(
    path: Union[str, Path],
    media_root: Optional[Union[str, Path]] = None,
) -> Dict[str, ImageRecord]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    images: Dict[str, ImageRecord] = {}
    media_directory = Path(media_root) if media_root is not None else None
    required_columns = {'image_id', 'user_id', 'request_id', 'related_event_id'}

    with open(path, mode='r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        available_columns = set(reader.fieldnames or [])
        if not required_columns.issubset(available_columns):
            missing = required_columns - available_columns
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            image_id = row.get('image_id')
            if not image_id or not image_id.strip():
                raise ValueError("Missing or blank image_id")
            if image_id in images:
                raise ValueError(f"Duplicate image_id found: {image_id}")

            media_reference = f"{image_id}.png"
            resolved_media_path = None
            if media_directory is not None:
                resolved_media_path = media_directory / media_reference
                if not resolved_media_path.is_file():
                    raise FileNotFoundError(
                        f"Missing media file for image {image_id}: "
                        f"{resolved_media_path}"
                    )

            images[image_id] = ImageRecord(
                image_id=image_id,
                user_id=row['user_id'],
                request_id=row['request_id'] if row['request_id'].strip() else None,
                related_event_id=(
                    row['related_event_id']
                    if row['related_event_id'].strip()
                    else None
                ),
                media_reference=media_reference,
                media_path=resolved_media_path,
            )

    return images

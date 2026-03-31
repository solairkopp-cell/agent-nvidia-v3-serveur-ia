# Delivery Completion State Machine

## Overview

This state machine manages the delivery completion workflow, allowing drivers to report delivery status through voice interaction.

## Architecture

### Modes

**MODE_0 - Normal Operation:**
```
STT → IntentDetector → KNOWN → Action → TTS
                     → UNKNOWN → LLM → TTS
```

**MODE_1 - Delivery Completion Flow:**
```
STT → Normalize → Pattern Matching → Action
```
No IntentDetector, no LLM in MODE_1.

### States (MODE_1)

```
┌─────────────────────────────────────────────────────────────┐
│                      MODE_1 Entry                            │
│            (triggered by start_delivery_completion)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │  STATE_1    │  "Is the delivery completed?"
              │ ASK_COMPLETION │
              └──────┬──────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
     YES           NO         INVALID
        │            │            │
        │            │            ├─→ Retry (max 2)
        │            │            │   "Sorry, I didn't understand..."
        │            │            └─→ Fallback → Reset STATE_1
        │            │
        │            ▼
        │     ┌─────────────┐
        │     │  STATE_2    │  "Can you tell me why?"
        │     │ ASK_REASON  │
        │     └──────┬──────┘
        │            │
        │   ┌────────┼────────┐
        │   │        │        │
        │   ▼        ▼        ▼
        │  LIST   NUMBER   INVALID
        │   │        │        │
        │   │        │        ├─→ Retry (max 2)
        │   │        │        └─→ Fallback → Reset STATE_1
        │   │        │
        │   │        └─→ Read reasons aloud
        │   │           Stay STATE_2
        │   │
        │   └─→ Extract number (1-N)
        │        │
        │        └─→ Map to reason
        │
        ▼            ▼
        └──────┬─────┘
               │
               ▼
        ┌─────────────┐
        │  STATE_4    │  Update trip status
        │   COMPLETE  │  SUCCESS: status="COMPLETED"
        │             │  FAILURE: status="FAILED", reason=N
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  STATE_5    │  Exit to MODE_0
        │    EXIT     │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │   MODE_0    │  Normal operation resumes
        └─────────────┘
```

## State Details

### STATE_1: ASK_COMPLETION

**TTS Prompt:** *"Is the delivery completed?"*

**Transitions:**
- **YES** → `STATE_4 (SUCCESS)` ✅ EXIT
  - Patterns: `yes`, `yeah`, `yep`, `oui`, `ok`, `okay`, `done`, `completed`, `finished`
- **NO** → `STATE_2`
  - Patterns: `no`, `nope`, `nah`, `non`, `not`, `failed`, `failure`, `problem`, `issue`
- **INVALID/TIMEOUT** → retry (max 2)
  - Retry message: *"Sorry, I didn't understand. Could you repeat?"*
- **Fallback** (after max retries) → TTS: *"Sorry, an error occurred. Let's start over."* → reset `STATE_1`

### STATE_2: ASK_REASON

**TTS Prompt:** *"Can you tell me why?"*

**Transitions:**
- **"list"** → read reasons aloud → stay `STATE_2`
  - Reads: *"Failure reasons: 1. Customer not available, 2. Wrong address, ..."*
- **NUMBER detected** → `STATE_4 (FAILURE)` ✅ EXIT
  - Uses `NumberExtractor` to parse spoken numbers (1-10, or digits)
  - Maps number to failure reason from configured list
- **NO NUMBER** → retry (max 2)
- **Fallback** → reset `STATE_1`

**Failure Reasons List:**
1. Customer not available
2. Wrong address
3. Package damaged
4. Access denied
5. Vehicle breakdown
6. Other

### STATE_4: COMPLETE

**Action:** Update trip status via PlanningService

- **SUCCESS** → `planning.update_trip(status="COMPLETED")`
- **FAILURE** → `planning.update_trip(status="FAILED", reason=N)`

**Transition:** → `STATE_5` (automatic)

### STATE_5: EXIT

**Action:** Return to MODE_0

- Clear state context
- Resume normal conversation flow

## Usage

### Starting the Delivery Completion Flow

```python
# From WebSocket handler or notification
await delivery_service.start_delivery_completion(session, trip_id="...")
```

This will:
1. Store `driver_serial` and `trip_id` in session
2. Enter `MODE_1 → STATE_1`
3. Trigger TTS: *"Is the delivery completed?"*

### State Machine Integration

The state machine is automatically checked in `AgentService._process_transcription()`:

```python
if self.state_machine.is_in_mode_1(session):
    result = await self.state_machine.process_input(session, transcript)
    if result.should_handle:
        # State machine handled it (no LLM)
        if result.tts_response:
            await self._speak_state_response(...)
        if result.action == "update_trip":
            await self._handle_update_trip_action(...)
        return  # Skip normal pipeline
# else: Continue with MODE_0 (intent detection → LLM)
```

## Configuration

Edit `StateMachineConfig` in `services/delivery_state_machine.py`:

```python
@dataclass
class StateMachineConfig:
    max_retries: int = 2
    retry_tts: str = "Sorry, I didn't understand. Could you repeat?"
    fallback_tts: str = "Sorry, an error occurred. Let's start over."
    
    # STATE_1
    ask_completion_tts: str = "Is the delivery completed?"
    yes_patterns: tuple = ("yes", "yeah", "yep", "oui", "ok", ...)
    no_patterns: tuple = ("no", "nope", "nah", "non", "not", ...)
    
    # STATE_2
    ask_reason_tts: str = "Can you tell me why?"
    list_trigger: str = "list"
    reason_list: tuple = ("Customer not available", "Wrong address", ...)
```

## NumberExtractor

Supports both digits and number words in English/French:

- **Digits:** `1`, `2`, `3`...
- **English:** `one`, `two`, `three`, `first`, `second`...
- **French:** `un`, `deux`, `trois`, `premier`, `deuxième`...

Example:
```python
NumberExtractor.extract("I choose number 3")      # → 3
NumberExtractor.extract("the first one")          # → 1
NumberExtractor.extract("raison numéro deux")     # → 2
```

## Session Fields

Added to `models/session.py`:

```python
@dataclass
class Session:
    # ... existing fields ...
    
    # Delivery State Machine
    driver_serial: Optional[str] = None      # Driver's serial number
    current_trip_id: Optional[str] = None    # Trip being completed
```

## Files Modified/Created

**Created:**
- `services/delivery_state_machine.py` - Main state machine logic

**Modified:**
- `services/agent_service.py` - Integration with pipeline
- `services/delivery_service.py` - `start_delivery_completion()` method
- `models/session.py` - Added `driver_serial`, `current_trip_id` fields
- `main.py` - State machine instantiation and lifecycle

## Testing

To test the state machine:

1. Start the server
2. Connect a WebSocket client
3. Send `identify_driver` with `driver_serial`
4. Call `start_delivery_completion(session)` (e.g., via API or UI button)
5. Speak responses:
   - "No" → Should ask for reason
   - "List" → Should read reasons
   - "3" → Should update trip with reason #3
   - Should return to normal mode

## Error Handling

- **Missing driver_serial:** Logs warning, stays in MODE_0
- **Missing trip_id:** Logs warning, stays in MODE_0
- **PlanningService error:** Logs error, continues to exit
- **Max retries exceeded:** Fallback message, reset to STATE_1
- **State machine exception:** Caught, continues with normal MODE_0 pipeline

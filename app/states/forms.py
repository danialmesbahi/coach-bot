from aiogram.fsm.state import State, StatesGroup

class PurchaseForm(StatesGroup):
    custom_question = State()
    name = State(); phone = State(); age = State(); gender = State(); height = State(); weight = State()
    allergy = State(); restriction = State(); supplements = State()
    goal = State(); training_history = State(); notes = State(); body_photo = State(); confirm = State(); payment_method = State(); submitting = State(); receipt = State()

class EditForm(StatesGroup):
    value = State()

class SupportForm(StatesGroup):
    waiting = State()

class NeedInfoForm(StatesGroup):
    waiting = State()

class PlanDelivery(StatesGroup):
    waiting = State()

class CancelOrder(StatesGroup):
    confirm = State()

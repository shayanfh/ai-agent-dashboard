from app.modules.knowledge_base.schemas import KBTemplateResponse


KNOWLEDGE_BASE_TEMPLATES = [
    KBTemplateResponse(
        business_type="restaurant",
        name="Restaurant starter knowledge",
        description="Common restaurant, menu, reservation, delivery, and allergy questions.",
        items=[
            {
                "category": "hours",
                "question": "What are your opening hours?",
                "answer": "Replace this answer with the restaurant's opening hours for each day.",
            },
            {
                "category": "location",
                "question": "Where is the restaurant located?",
                "answer": "Replace this answer with the full address, landmarks, and parking details.",
            },
            {
                "category": "reservations",
                "question": "Can I reserve a table?",
                "answer": "Yes. Ask for the date, time, party size, guest name, and contact number. Do not confirm availability unless the reservation system confirms it.",
            },
            {
                "category": "reservations",
                "question": "What is your reservation cancellation policy?",
                "answer": "Replace this answer with the cancellation, late-arrival, deposit, and no-show policy.",
            },
            {
                "category": "menu",
                "question": "What food do you serve?",
                "answer": "Replace this answer with a short description of the cuisine and the most popular dishes.",
            },
            {
                "category": "menu",
                "question": "Do you have vegetarian or vegan options?",
                "answer": "Replace this answer with the available vegetarian and vegan dishes and customization policy.",
            },
            {
                "category": "allergies",
                "question": "Can you accommodate food allergies?",
                "answer": "Never guarantee that a dish is allergen-free. Record the allergy and ask restaurant staff to confirm ingredients and cross-contamination risk.",
            },
            {
                "category": "delivery",
                "question": "Do you offer delivery or takeaway?",
                "answer": "Replace this answer with delivery areas, ordering channels, fees, minimum order, and collection instructions.",
            },
            {
                "category": "groups",
                "question": "Can you accommodate large groups or private events?",
                "answer": "Replace this answer with maximum group size, private room availability, set-menu requirements, and deposit policy.",
            },
            {
                "category": "accessibility",
                "question": "Is the restaurant accessible?",
                "answer": "Replace this answer with wheelchair access, accessible restroom, lift, and assistance information.",
            },
        ],
    ),
    KBTemplateResponse(
        business_type="car_rental",
        name="Car rental starter knowledge",
        description="Common fleet, eligibility, pricing, insurance, pickup, and return questions.",
        items=[
            {
                "category": "eligibility",
                "question": "What do I need to rent a car?",
                "answer": "Replace this answer with the accepted driving licences, identification, payment card, minimum driving experience, and age requirements.",
            },
            {
                "category": "eligibility",
                "question": "What is the minimum driver age?",
                "answer": "Replace this answer with the minimum age and any young-driver fee or vehicle restrictions.",
            },
            {
                "category": "fleet",
                "question": "What types of vehicles are available?",
                "answer": "Replace this answer with vehicle categories, passenger and luggage capacity, transmission type, and key features. Never promise a specific model unless confirmed.",
            },
            {
                "category": "pricing",
                "question": "What is included in the rental price?",
                "answer": "Replace this answer with included mileage, taxes, basic insurance, roadside assistance, and excluded fees.",
            },
            {
                "category": "insurance",
                "question": "What insurance options are available?",
                "answer": "Replace this answer with coverage options, excess amounts, exclusions, and optional protection. Do not provide legal advice.",
            },
            {
                "category": "deposit",
                "question": "Is a security deposit required?",
                "answer": "Replace this answer with the deposit amount or calculation, accepted cards, authorization timing, and release period.",
            },
            {
                "category": "pickup_return",
                "question": "Where can I pick up and return the vehicle?",
                "answer": "Replace this answer with branch locations, opening hours, airport instructions, and one-way rental availability.",
            },
            {
                "category": "pickup_return",
                "question": "What happens if I return the car late?",
                "answer": "Replace this answer with the grace period, extension process, late fees, and after-hours return procedure.",
            },
            {
                "category": "fuel_mileage",
                "question": "What are the fuel and mileage policies?",
                "answer": "Replace this answer with the fuel policy, included mileage, excess mileage rate, and electric vehicle charging policy.",
            },
            {
                "category": "changes",
                "question": "Can I change or cancel my booking?",
                "answer": "Replace this answer with modification deadlines, cancellation fees, refund timing, and no-show policy.",
            },
            {
                "category": "additional_driver",
                "question": "Can I add another driver?",
                "answer": "Replace this answer with additional-driver eligibility, required documents, and daily fee.",
            },
            {
                "category": "breakdown",
                "question": "What should I do after an accident or breakdown?",
                "answer": "Prioritize safety and emergency services. Replace this answer with the roadside assistance number, accident reporting steps, and prohibited actions.",
            },
        ],
    ),
]


def get_knowledge_template(business_type: str) -> KBTemplateResponse | None:
    normalized = business_type.strip().lower()
    return next(
        (item for item in KNOWLEDGE_BASE_TEMPLATES if item.business_type == normalized),
        None,
    )

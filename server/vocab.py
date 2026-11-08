"""
vocab.py - AdaptiBoard's built-in vocabulary.

Each line is  label | part-of-speech | emoji fallback | (optional) spoken text
Parts of speech decide the AAC colour of the tile (see web/src/lib/colors.ts):

    pronoun  -> yellow   (people / pronouns)
    verb     -> green    (actions)
    noun     -> orange   (things / food)
    place    -> orange   (places)
    social   -> pink     (social words / phrases)
    no       -> soft red (no / stop / urgent)
    yes      -> soft green (yes / go)
    describe -> blue     (describing words, feelings)
    question -> purple   (question words)
    little   -> slate    (little grammar words: to, the, and ...)

Pictograms come from ARASAAC (fetched + cached by icons.py). The emoji is the
fallback when there's no internet or no good pictogram.
"""

# Side menu (Back is added by the board itself).
CATEGORIES = [
    # id, label, emoji
    ("smart", "Smart Board", "✨"),
    ("more", "More words", "📚"),
    ("keyboard", "Keyboard", "⌨️"),
    ("chat", "Chat", "💬"),
    ("needs", "Needs", "🆘"),
]

# "More words" (under the Smart Board): category -> its words.
MORE_CATEGORIES = [
    # id, label, emoji, colour (part of speech)
    ("people", "People", "👥", "pronoun"),
    ("actions", "Actions", "🏃", "verb"),
    ("feelings", "Feelings", "💛", "describe"),
    ("food", "Food & Drink", "🍽️", "noun"),
    ("places", "Places", "📍", "place"),
    ("things", "Things", "🧸", "noun"),
    ("questions", "Questions", "❓", "question"),
    ("describe", "Describe", "🎨", "describe"),
    ("body", "Body", "🫀", "noun"),
    ("time", "Time", "🕒", "describe"),
    ("activities", "Activities", "🎲", "verb"),
    ("little", "Little words", "🔤", "little"),
]

_RAW = {
    "people": """
        I|pronoun|🙋
        you|pronoun|🫵
        we|pronoun|👫
        he|pronoun|👦
        she|pronoun|👧
        they|pronoun|👪
        me|pronoun|🙋
        my|pronoun|☝️
        mom|pronoun|👩
        dad|pronoun|👨
        family|pronoun|👨‍👩‍👧
        friend|pronoun|🤝
        doctor|pronoun|🧑‍⚕️
        nurse|pronoun|👩‍⚕️
        brother|pronoun|👦
        sister|pronoun|👧
        teacher|pronoun|🧑‍🏫
        baby|pronoun|👶
        everyone|pronoun|👥
        your|pronoun|👉
        grandma|pronoun|👵
        grandpa|pronoun|👴
        son|pronoun|👦
        daughter|pronoun|👧
        husband|pronoun|🧔
        wife|pronoun|👩
        partner|pronoun|💑
        caregiver|pronoun|🧑‍⚕️
        aunt|pronoun|👩
        uncle|pronoun|👨
    """,
    "actions": """
        want|verb|🤲
        need|verb|❗
        like|verb|👍
        go|yes|🟢
        eat|verb|🍴
        drink|verb|🥤
        help|verb|🤝
        stop|no|✋
        play|verb|🎲
        sleep|verb|😴
        look|verb|👀
        watch|verb|📺
        listen|verb|👂
        talk|verb|🗣️
        feel|verb|🫶
        have|verb|🤲
        love|verb|❤️
        get|verb|📦
        make|verb|🛠️
        come|verb|👋
        see|verb|👁️
        read|verb|📖
        sit|verb|🪑
        wait|verb|⏳
        call|verb|📞
        give|verb|🎁
        open|verb|📂
        close|verb|🚪
        turn on|verb|💡
        turn off|verb|🌑
        think|verb|💭
        know|verb|🧠
        am|verb|🟰
        is|verb|🟰
        can|verb|💪
        don't|no|🚫
        hug|verb|🤗
        finish|verb|🏁
        wash|verb|🧼
        move|verb|↔️
    """,
    "feelings": """
        happy|describe|😊
        sad|describe|😢
        tired|describe|😴
        hungry|describe|🍽️
        thirsty|describe|🥤
        sick|describe|🤒
        in pain|no|🤕
        okay|describe|👌
        good|describe|👍
        bad|describe|👎
        scared|describe|😨
        angry|describe|😠
        bored|describe|🥱
        excited|describe|🤩
        hot|describe|🥵
        cold|describe|🥶
        worried|describe|😟
        calm|describe|😌
        lonely|describe|🥺
        uncomfortable|describe|😣
        confused|describe|😕
        frustrated|describe|😤
        proud|describe|🥲
        nervous|describe|😬
    """,
    "food": """
        water|noun|💧
        food|noun|🍽️
        juice|noun|🧃
        milk|noun|🥛
        coffee|noun|☕
        tea|noun|🍵
        breakfast|noun|🥞
        lunch|noun|🥪
        dinner|noun|🍲
        snack|noun|🍪
        apple|noun|🍎
        banana|noun|🍌
        pizza|noun|🍕
        pasta|noun|🍝
        rice|noun|🍚
        soup|noun|🥣
        sandwich|noun|🥪
        chicken|noun|🍗
        eggs|noun|🍳
        bread|noun|🍞
        salad|noun|🥗
        cereal|noun|🥣
        ice cream|noun|🍨
        chocolate|noun|🍫
        cheese|noun|🧀
        burger|noun|🍔
        fries|noun|🍟
        grapes|noun|🍇
        strawberry|noun|🍓
        yogurt|noun|🍦
        cookie|noun|🍪
        soda|noun|🥤
    """,
    "places": """
        home|place|🏠
        bathroom|place|🚻
        bed|place|🛏️
        outside|place|🌳
        kitchen|place|🍳
        bedroom|place|🛌
        park|place|🏞️
        school|place|🏫
        hospital|place|🏥
        store|place|🏪
        restaurant|place|🍽️
        car|place|🚗
        work|place|💼
        beach|place|🏖️
        garden|place|🌷
        living room|place|🛋️
        church|place|⛪
        library|place|📚
    """,
    "things": """
        phone|noun|📱
        TV|noun|📺
        music|noun|🎵
        book|noun|📖
        tablet|noun|📲
        computer|noun|💻
        glasses|noun|👓
        blanket|noun|🛏️
        pillow|noun|🛌
        clothes|noun|👕
        shoes|noun|👟
        wheelchair|noun|🦽
        medicine|noun|💊
        game|noun|🎮
        ball|noun|⚽
        toy|noun|🧸
        light|noun|💡
        door|noun|🚪
        window|noun|🪟
        remote|noun|🎛️
        bag|noun|👜
        money|noun|💵
        picture|noun|🖼️
        keys|noun|🔑
    """,
    "describe": """
        more|describe|➕
        all done|no|✅
        big|describe|🐘
        small|describe|🐭
        hot|describe|🔥
        cold|describe|🧊
        now|describe|⏰
        later|describe|🕒
        again|describe|🔁
        fast|describe|⚡
        slow|describe|🐢
        loud|describe|🔊
        quiet|describe|🤫
        different|describe|🔀
        same|describe|🟰
        here|describe|📍
        there|describe|👉
        not|no|🚫
        too|describe|➕
        very|describe|❗
        all|describe|🔢
        broken|describe|💔
        dirty|describe|🟤
        clean|describe|✨
        wet|describe|💦
        ready|describe|👍
    """,
    "body": """
        head|noun|🗣️
        eyes|noun|👀
        ears|noun|👂
        nose|noun|👃
        mouth|noun|👄
        teeth|noun|🦷
        throat|noun|🗣️
        neck|noun|🧣
        shoulder|noun|💪
        chest|noun|🫁
        heart|noun|❤️
        stomach|noun|🤰
        back|noun|🧍
        arm|noun|💪
        hand|noun|✋
        leg|noun|🦵
        foot|noun|🦶
        skin|noun|🖐️
    """,
    "time": """
        now|describe|⏰
        later|describe|🕒
        today|describe|📅
        tomorrow|describe|➡️
        yesterday|describe|⬅️
        morning|describe|🌅
        afternoon|describe|🌤️
        evening|describe|🌇
        night|describe|🌙
        soon|describe|⏳
        before|describe|⏮️
        after|describe|⏭️
        weekend|describe|🎉
        birthday|describe|🎂
        minute|describe|⏱️
        hour|describe|🕐
    """,
    "activities": """
        music|noun|🎵
        movie|noun|🎬
        walk|verb|🚶
        shower|noun|🚿
        bath|noun|🛁
        game|noun|🎮
        read|verb|📖
        draw|verb|🎨
        sing|verb|🎤
        dance|verb|💃
        swim|verb|🏊
        exercise|verb|🏋️
        cook|verb|🍳
        shopping|noun|🛍️
        video call|noun|📹
        puzzle|noun|🧩
    """,
    "little": """
        to|little|➡️
        the|little|▫️
        a|little|▫️
        and|little|➕
        with|little|🤝
        for|little|🎯
        in|little|📥
        on|little|🔛
        at|little|📍
        of|little|▫️
        my|pronoun|☝️
        your|pronoun|👉
        it|pronoun|📦
        that|pronoun|👉
        this|pronoun|👇
        is|verb|🟰
        are|verb|🟰
        not|no|🚫
        but|little|↔️
        or|little|🔀
        because|little|💡
        from|little|⬅️
        some|little|▫️
        up|little|⬆️
        out|little|↗️
    """,
    "questions": """
        what|question|❓
        where|question|📍
        when|question|🕒
        who|question|👤
        why|question|🤔
        how|question|🛠️
        which|question|🔢
        how much|question|💲
        can I|question|🙋
        can you|question|🫵
        are you|question|❔
        do you|question|❔
        is it|question|❔
        what time is it?|question|⏰
        what's that?|question|👉
        how are you?|question|💬
    """,
    "chat": """
        hello|social|👋
        goodbye|social|👋
        thank you|social|🙏
        please|social|🥺
        yes|yes|✅
        no|no|❌
        sorry|social|😔
        I love you|social|❤️
        how are you?|social|💬
        I'm fine|social|🙂
        excuse me|social|🙋
        I don't know|social|🤷
        maybe|social|🤔
        me too|social|🙌
        good morning|social|🌅
        good night|social|🌙
        see you later|social|👋
        that's funny|social|😂
        wait a minute|social|⏳
        you're welcome|social|😊
        never mind|social|🙃
        I agree|social|👍
    """,
}


def _parse():
    words = {}  # lower label -> entry (first definition wins for pos/emoji)
    cats = {}
    for cat, block in _RAW.items():
        items = []
        for line in block.strip().splitlines():
            parts = [p.strip() for p in line.strip().split("|")]
            label, pos, emoji = parts[0], parts[1], parts[2]
            speak = parts[3] if len(parts) > 3 else label
            entry = {"label": label, "pos": pos, "emoji": emoji, "speak": speak,
                     "kind": "phrase" if speak != label or " " in label else "word"}
            items.append(entry)
            words.setdefault(label.lower(), {**entry, "speak": label, "kind": "word" if " " not in label else "phrase"})
        cats[cat] = items
    return words, cats


WORDS, CATEGORY_WORDS = _parse()

# Small extra lexicon of parts of speech for words the LLM/transcript may produce.
EXTRA_POS = {
    "yes": "yes", "no": "no", "okay": "yes", "sure": "yes", "go": "yes", "stop": "no",
    "not": "no", "don't": "no", "never": "no", "won't": "no", "can't": "no",
    "please": "social", "thanks": "social",
}

STOPWORDS = set("""
a an the and or but if then so of to in on at by for with from up down out over under
is am are was were be been being do does did doing have has had having will would shall
should can could may might must i you he she it we they me him her us them my your his
its our their mine yours this that these those there here what which who whom whose when
where why how all any both each few more most other some such no nor not only own same
than too very just also now well oh hey yeah yep uh um like okay ok really get got go
going gonna want wanna let lets let's dont don't im i'm you're youre it's its thats that's
know think see say said tell told one two thing things something anything nothing time
right good great sounds sound make made way much many lot lots little bit maybe today
tonight tomorrow yesterday later soon still again back come came take took give gave put
""".split())

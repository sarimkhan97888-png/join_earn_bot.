"""Bhasha table. Key = code me likha Hinglish template ({} = badalne wali value), value = (Hindi, English).
{} ki ginti aur HTML tags dono bhasha me same rahen. Value ka order badalna ho to {0},{1} use karo (sab ya koi nahi)."""

# bade fixed text (jahan message dusre text ke saath jod ke bheja jata hai)
CONSTS = {
    "💰 <b>𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄 𝐓𝐀𝐒𝐊𝐒 &amp; 𝐄𝐀𝐑𝐍 𝐂𝐎𝐈𝐍𝐒</b> 🪙\n\n"
    "🔥 Complete Tasks &amp; Earn Coins\n"
    "💸 Instant UPI Withdrawal\n"
    "🎯 Create Tasks Using Coins\n"
    "📺 Watch Ads &amp; Earn Rewards\n"
    "👥 Get Subscribers &amp; Referrals\n\n"
    "🚀 <b>𝐒𝐭𝐚𝐫𝐭 𝐄𝐚𝐫𝐧𝐢𝐧𝐠 𝐓𝐨𝐝𝐚𝐲!</b> 💎": (
        "💰 <b>𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄 𝐓𝐀𝐒𝐊𝐒 &amp; 𝐄𝐀𝐑𝐍 𝐂𝐎𝐈𝐍𝐒</b> 🪙\n\n"
        "🔥 टास्क पूरे करो और कॉइन्स कमाओ\n"
        "💸 तुरंत UPI विड्रॉ\n"
        "🎯 कॉइन्स से अपने टास्क बनाओ\n"
        "📺 विज्ञापन देखो और इनाम कमाओ\n"
        "👥 सब्सक्राइबर और रेफ़रल पाओ\n\n"
        "🚀 <b>आज ही कमाना शुरू करो!</b> 💎",
        "💰 <b>𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄 𝐓𝐀𝐒𝐊𝐒 &amp; 𝐄𝐀𝐑𝐍 𝐂𝐎𝐈𝐍𝐒</b> 🪙\n\n"
        "🔥 Complete Tasks &amp; Earn Coins\n"
        "💸 Instant UPI Withdrawal\n"
        "🎯 Create Tasks Using Coins\n"
        "📺 Watch Ads &amp; Earn Rewards\n"
        "👥 Get Subscribers &amp; Referrals\n\n"
        "🚀 <b>𝐒𝐭𝐚𝐫𝐭 𝐄𝐚𝐫𝐧𝐢𝐧𝐠 𝐓𝐨𝐝𝐚𝐲!</b> 💎"),
}

SERVER = {}


def _add(d):
    SERVER.update(d)


# ---------------- general / API errors ----------------
_add({
    "Thoda ruko, bahut tez kar rahe ho.": ("थोड़ा रुको, तुम बहुत तेज़ी से कर रहे हो।", "Slow down, you're going too fast."),
    "Bahut tez! Thoda ruko.": ("बहुत तेज़! थोड़ा रुको।", "Too fast! Please wait a moment."),
    "⚠️ Server error. Thodi der baad try karo.": ("⚠️ सर्वर में गड़बड़ है। थोड़ी देर बाद कोशिश करो।", "⚠️ Server error. Please try again in a while."),
    "🚫 Account banned.": ("🚫 अकाउंट बैन है।", "🚫 Account banned."),
    "🔐 Pehle device verify karo.": ("🔐 पहले डिवाइस वेरिफाई करो।", "🔐 Please verify your device first."),
    "Galat bhasha.": ("गलत भाषा।", "Invalid language."),
    "✅ Bhasha badal gayi.": ("✅ भाषा बदल गई।", "✅ Language changed."),
    "🔔 Notification ON": ("🔔 नोटिफिकेशन चालू", "🔔 Notification ON"),
    "🔕 Notification OFF": ("🔕 नोटिफिकेशन बंद", "🔕 Notification OFF"),
    "Already verified": ("पहले से वेरिफाइड है", "Already verified"),
    "Device check fail hua. App band karke dobara kholo.": ("डिवाइस चेक फेल हो गया। ऐप बंद करके दोबारा खोलो।", "Device check failed. Close the app and open it again."),
    "🚫 Device verification fail. Account block hai, Customer service se contact karo.": ("🚫 डिवाइस वेरिफिकेशन फेल। अकाउंट ब्लॉक है, कस्टमर सर्विस से संपर्क करो।", "🚫 Device verification failed. Your account is blocked, please contact Customer service."),
    "Device verified! Bot par wapas jao aur Open App dabao.": ("डिवाइस वेरिफाई हो गया! बॉट पर वापस जाओ और Open App दबाओ।", "Device verified! Go back to the bot and tap Open App."),
    "✅ <b>Device verify ho gaya!</b>": ("✅ <b>डिवाइस वेरिफाई हो गया!</b>", "✅ <b>Device verified!</b>"),
    "👇 Ab app kholo": ("👇 अब ऐप खोलो", "👇 Now open the app"),
    "🚫 <b>Device verification fail</b>\nYe device kisi aur account se linked hai ya tumhara account pehle kisi aur device se verify tha. Account block hai, Customer service se contact karo.": (
        "🚫 <b>डिवाइस वेरिफिकेशन फेल</b>\nये डिवाइस किसी और अकाउंट से जुड़ा है, या तुम्हारा अकाउंट पहले किसी और डिवाइस से वेरिफाई था। अकाउंट ब्लॉक है, कस्टमर सर्विस से संपर्क करो।",
        "🚫 <b>Device verification failed</b>\nThis device is linked to another account, or your account was verified on another device earlier. Your account is blocked, please contact Customer service."),
})

# ---------------- tasks / channels ----------------
_add({
    "Unblocked! Ab tasks kar sakte ho.": ("अनब्लॉक हो गया! अब तुम टास्क कर सकते हो।", "Unblocked! You can do tasks now."),
    "Unblocked! Ab tasks kar sakte ho. {} coins ({}%) {}h hold me mile.": ("अनब्लॉक हो गया! अब तुम टास्क कर सकते हो। {} कॉइन्स ({}%) {} घंटे होल्ड में मिले।", "Unblocked! You can do tasks now. {} coins ({}%) received, on hold for {}h."),
    "🔐 Pehle Profile me device verify karo.": ("🔐 पहले प्रोफ़ाइल में डिवाइस वेरिफाई करो।", "🔐 Please verify your device in Profile first."),
    "🚫 Tum blocked ho. Pehle left channel rejoin karo.": ("🚫 तुम ब्लॉक हो। पहले छोड़े हुए चैनल दोबारा जॉइन करो।", "🚫 You are blocked. Please rejoin the channels you left first."),
    "Ye task ab available nahi.": ("ये टास्क अब उपलब्ध नहीं है।", "This task is no longer available."),
    "Ye task tum pehle kar chuke ho.": ("ये टास्क तुम पहले कर चुके हो।", "You have already done this task."),
    "Apne channel se coin nahi mil sakta.": ("अपने चैनल से कॉइन नहीं मिल सकता।", "You can't earn coins from your own channel."),
    "Task full ho gaya.": ("टास्क फुल हो गया।", "This task is full."),
    "⚠️ Verify nahi ho paya. Thodi der baad try karo.": ("⚠️ वेरिफाई नहीं हो पाया। थोड़ी देर बाद कोशिश करो।", "⚠️ Couldn't verify. Please try again in a while."),
    "❌ Pehle channel join karo, phir Check dabao.": ("❌ पहले चैनल जॉइन करो, फिर Check दबाओ।", "❌ Join the channel first, then tap Check."),
    "❌ Join record nahi mila. Channel leave karke dobara join karo, phir Check dabao.": ("❌ जॉइन का रिकॉर्ड नहीं मिला। चैनल छोड़कर दोबारा जॉइन करो, फिर Check दबाओ।", "❌ Join record not found. Leave the channel and join again, then tap Check."),
    "Join verified! +{} coins ({}h hold me)": ("जॉइन वेरिफाई हुआ! +{} कॉइन्स ({} घंटे होल्ड में)", "Join verified! +{} coins ({}h on hold)"),
    "❌ Abhi bhi kuch channels join nahi kiye.": ("❌ अभी भी कुछ चैनल जॉइन नहीं किए।", "❌ You still haven't joined some channels."),
    "Pehle Premium lo.": ("पहले प्रीमियम लो।", "Get Premium first."),
    "Aaj ki task limit ({}) poori ho gayi. Level upgrade karo ya kal dobara banao.": ("आज की टास्क लिमिट ({}) पूरी हो गई। लेवल अपग्रेड करो या कल दोबारा बनाओ।", "Today's task limit ({}) is reached. Upgrade your level or create again tomorrow."),
    "Aaj ki task limit ({}) poori ho gayi. Kal dobara banao.": ("आज की टास्क लिमिट ({}) पूरी हो गई। कल दोबारा बनाओ।", "Today's task limit ({}) is reached. Create again tomorrow."),
    "❌ Channel ka @username ya t.me link daalo.": ("❌ चैनल का @username या t.me लिंक डालो।", "❌ Enter the channel's @username or t.me link."),
    "❌ Chat nahi mili. Bot ko pehle us channel/group me Admin banao aur sahi @username do.": ("❌ चैट नहीं मिली। पहले बॉट को उस चैनल/ग्रुप में एडमिन बनाओ और सही @username दो।", "❌ Chat not found. Make the bot an Admin in that channel/group first and give the correct @username."),
    "❌ Sirf channel ya group allowed hai.": ("❌ सिर्फ़ चैनल या ग्रुप चलेगा।", "❌ Only a channel or group is allowed."),
    "❌ Bot is chat me Admin nahi hai. @{} ko Admin banao (Invite Users permission ke saath).": ("❌ बॉट इस चैट में एडमिन नहीं है। @{} को एडमिन बनाओ (Invite Users परमिशन के साथ)।", "❌ The bot is not an Admin in this chat. Make @{} an Admin (with Invite Users permission)."),
    "❌ Tum is chat ke admin/owner nahi ho.": ("❌ तुम इस चैट के एडमिन/ओनर नहीं हो।", "❌ You are not an admin/owner of this chat."),
    "❌ Invite link nahi ban paya. Bot ko 'Invite Users' permission do.": ("❌ इन्वाइट लिंक नहीं बन पाया। बॉट को 'Invite Users' परमिशन दो।", "❌ Couldn't create an invite link. Give the bot the 'Invite Users' permission."),
    "Members {} se {} ke beech rakho.": ("मेंबर्स {} से {} के बीच रखो।", "Keep members between {} and {}."),
    "Coins kam hain. Chahiye {}, tumhare paas {} (ad balance + earnings). Wallet se deposit karo ya aur kamao.": ("कॉइन्स कम हैं। चाहिए {}, तुम्हारे पास {} (ऐड बैलेंस + कमाई)। वॉलेट से डिपॉज़िट करो या और कमाओ।", "Not enough coins. You need {}, you have {} (ad balance + earnings). Deposit from Wallet or earn more."),
    "Ad balance kam hai. Pehle deposit karo.": ("ऐड बैलेंस कम है। पहले डिपॉजिट करो।", "Ad balance is low. Please deposit first."),
    "Task #{} live ho gaya! {} ke liye {} members. Har joiner ko {} coins milenge.": ("टास्क #{} लाइव हो गया! {} के लिए {} मेंबर्स। हर जॉइन करने वाले को {} कॉइन्स मिलेंगे।", "Task #{} is live! {} for {} members. Each joiner gets {} coins."),
    "Tumhare level me ek task me max {} members. Zyada ke liye Premium upgrade karo.": ("तुम्हारे लेवल में एक टास्क में मैक्स {} मेंबर्स। ज़्यादा के लिए प्रीमियम अपग्रेड करो।", "Your level allows up to {} members per task. Upgrade Premium for more."),
    "Per member price kam se kam {} coins rakho.": ("हर मेंबर का प्राइस कम से कम {} कॉइन्स रखो।", "Set the per-member price to at least {} coins."),
    "✅ Tumhara task #{} live ho gaya: {} ({} members).": ("✅ तुम्हारा टास्क #{} लाइव हो गया: {} ({} मेंबर्स)।", "✅ Your task #{} is live: {} ({} members)."),
    "Task cancel hua. {} coins refund hue.": ("टास्क कैंसिल हुआ। {} कॉइन्स रिफंड हुए।", "Task cancelled. {} coins refunded."),
    "Ye task cancel nahi ho sakta.": ("ये टास्क कैंसिल नहीं हो सकता।", "This task can't be cancelled."),
    "Ye bot work cancel nahi ho sakta.": ("ये बॉट वर्क कैंसिल नहीं हो सकता।", "This bot work can't be cancelled."),
    "Bot work cancel hua. {} coins refund hue.": ("बॉट वर्क कैंसिल हुआ। {} कॉइन्स रिफंड हुए।", "Bot work cancelled. {} coins refunded."),
    "Bot work #{} live ho gaya!": ("बॉट वर्क #{} लाइव हो गया!", "Bot work #{} is live!"),
    "✅ Tumhara Bot Work #{} live ho gaya: {}.": ("✅ तुम्हारा बॉट वर्क #{} लाइव हो गया: {}।", "✅ Your Bot Work #{} is live: {}."),
    "Title 3 se 40 characters ka rakho.": ("टाइटल 3 से 40 अक्षरों का रखो।", "Keep the title between 3 and 40 characters."),
    "Sahi refer link daalo (https://...).": ("सही रेफ़र लिंक डालो (https://...)।", "Enter a valid refer link (https://...)."),
    "Reward min {} coins hona chahiye.": ("रिवॉर्ड कम से कम {} कॉइन्स होना चाहिए।", "Reward must be at least {} coins."),
    "Users {} se {} ke beech rakho.": ("यूज़र्स {} से {} के बीच रखो।", "Keep users between {} and {}."),
    "Coins kam hain. Chahiye {} coins (ad balance + earnings). Wallet se deposit karo ya aur kamao.": ("कॉइन्स कम हैं। {} कॉइन्स चाहिए (ऐड बैलेंस + कमाई)। वॉलेट से डिपॉज़िट करो या और कमाओ।", "Not enough coins. You need {} coins (ad balance + earnings). Deposit from Wallet or earn more."),
})

# ---------------- bot work (worker side) ----------------
_add({
    "Screenshot (photo) upload karo.": ("स्क्रीनशॉट (फोटो) अपलोड करो।", "Upload a screenshot (photo)."),
    "Screenshot 5MB se chhota bhejo.": ("स्क्रीनशॉट 5MB से छोटा भेजो।", "Send a screenshot smaller than 5MB."),
    "Is bot me device verification hai: 2 photo chahiye. Dusri photo me device verification ka result (success ya failed) dikhao.": ("इस बॉट में डिवाइस वेरिफिकेशन है: 2 फोटो चाहिए। दूसरी फोटो में डिवाइस वेरिफिकेशन का रिज़ल्ट (सक्सेस या फेल) दिखाओ।", "This bot has device verification: 2 photos needed. Show the device verification result (success or failed) in the second photo."),
    "Dono photo alag-alag hone chahiye.": ("दोनों फोटो अलग-अलग होनी चाहिए।", "Both photos must be different."),
    "Us bot ka sahi refer link daalo (https://...).": ("उस बॉट का सही रेफ़र लिंक डालो (https://...)।", "Enter that bot's valid refer link (https://...)."),
    "Tum ye task pehle submit kar chuke ho, ya ye screenshot pehle use ho chuka hai.": ("तुम ये टास्क पहले सबमिट कर चुके हो, या ये स्क्रीनशॉट पहले इस्तेमाल हो चुका है।", "You have already submitted this task, or this screenshot was used before."),
    "Apna hi task nahi kar sakte.": ("अपना ही टास्क नहीं कर सकते।", "You can't do your own task."),
    "Is task me tumhare 2 try ho chuke hain, ab ye task tumhare liye lock hai.": ("इस टास्क में तुम्हारी 2 कोशिशें हो चुकी हैं, अब ये टास्क तुम्हारे लिए लॉक है।", "You have used 2 tries on this task, it is now locked for you."),
    "Is task ke saare slots full ho gaye.": ("इस टास्क के सारे स्लॉट फुल हो गए।", "All slots of this task are full."),
    "Upload fail hua. Dobara try karo.": ("अपलोड फेल हुआ। दोबारा कोशिश करो।", "Upload failed. Please try again."),
    "Owner tak bhej nahi paya (unhone bot start nahi kiya hoga). Baad me try karo.": ("ओनर तक नहीं भेज पाया (शायद उन्होंने बॉट स्टार्ट नहीं किया होगा)। बाद में कोशिश करो।", "Couldn't reach the owner (they may not have started the bot). Try again later."),
    "Submit ho gaya! Status: Pending. Owner check karke Done karega to coins mil jayenge.": ("सबमिट हो गया! स्टेटस: पेंडिंग। ओनर चेक करके Done करेगा तो कॉइन्स मिल जाएंगे।", "Submitted! Status: Pending. You'll get coins once the owner checks and taps Done."),
    "Ye report nahi ho sakta (already reported ya time khatam).": ("ये रिपोर्ट नहीं हो सकता (पहले ही रिपोर्ट हो चुका या समय खत्म)।", "This can't be reported (already reported or time is over)."),
    "Report bhej di gayi. Admin check karke decision lega.": ("रिपोर्ट भेज दी गई। एडमिन चेक करके फ़ैसला लेगा।", "Report sent. Admin will check and decide."),
    "🤖 <b>Bot Work submission</b> #{}": ("🤖 <b>बॉट वर्क सबमिशन</b> #{}", "🤖 <b>Bot Work submission</b> #{}"),
    "Task: {}": ("टास्क: {}", "Task: {}"),
    "Worker: {} (<code>{}</code>)": ("वर्कर: {} (<code>{}</code>)", "Worker: {} (<code>{}</code>)"),
    "Refer link: {}": ("रेफ़र लिंक: {}", "Refer link: {}"),
    "Reward: {} coins": ("रिवॉर्ड: {} कॉइन्स", "Reward: {} coins"),
    "Screenshot dekho. Sahi ho to <b>Done</b>, nahi to Reject.": ("स्क्रीनशॉट देखो। सही हो तो <b>Done</b>, नहीं तो Reject।", "Check the screenshot. Tap <b>Done</b> if correct, otherwise Reject."),
    "🔐 Is bot me device verification hai: upar wali alag photo me uska result dekho.": ("🔐 इस बॉट में डिवाइस वेरिफिकेशन है: ऊपर वाली अलग फोटो में उसका रिज़ल्ट देखो।", "🔐 This bot has device verification: see its result in the separate photo above."),
    "🔐 <b>Device verification screenshot</b> (submission #{}). Result success hai ya failed, dekho.": ("🔐 <b>डिवाइस वेरिफिकेशन स्क्रीनशॉट</b> (सबमिशन #{})। देखो रिज़ल्ट सक्सेस है या फेल।", "🔐 <b>Device verification screenshot</b> (submission #{}). Check whether the result is success or failed."),
    "Reason thoda detail me likho (kam se kam 3 akshar).": ("रीज़न थोड़ा डिटेल में लिखो (कम से कम 3 अक्षर)।", "Write the reason in a bit more detail (at least 3 characters)."),
    "Already processed ya ye task tumhara nahi hai.": ("पहले ही प्रोसेस हो चुका है या ये टास्क तुम्हारा नहीं है।", "Already processed, or this task isn't yours."),
    "Already processed ya tum is task ke owner nahi ho.": ("पहले ही प्रोसेस हो चुका है या तुम इस टास्क के ओनर नहीं हो।", "Already processed, or you aren't the owner of this task."),
    "✅ Reject ho gaya, worker ko reason bhej diya.": ("✅ रिजेक्ट हो गया, वर्कर को रीज़न भेज दिया।", "✅ Rejected, the reason was sent to the worker."),
    "✅ Done! Worker ko coins mil gaye.": ("✅ हो गया! वर्कर को कॉइन्स मिल गए।", "✅ Done! The worker received the coins."),
    "✅ Bot work approved! <b>+{}</b> coins balance me add ho gaye.": ("✅ बॉट वर्क अप्रूव हुआ! <b>+{}</b> कॉइन्स बैलेंस में जुड़ गए।", "✅ Bot work approved! <b>+{}</b> coins added to your balance."),
    "❌ Reject kar diya, worker ko reason bhej diya.": ("❌ रिजेक्ट कर दिया, वर्कर को रीज़न भेज दिया।", "❌ Rejected, the reason was sent to the worker."),
    "Reason chuno: worker ko ye dikhega": ("रीज़न चुनो: वर्कर को ये दिखेगा", "Choose a reason: the worker will see it"),
    "✍️ Reject ka reason ab likh ke bhejo (worker ko yahi dikhega, max 200 akshar).": ("✍️ रिजेक्ट का रीज़न अब लिखकर भेजो (वर्कर को यही दिखेगा, ज़्यादा से ज़्यादा 200 अक्षर)।", "✍️ Now send the reject reason in writing (the worker will see this, max 200 characters)."),
    "🚩 Report bhej di gayi. Admin check karke decision lega.": ("🚩 रिपोर्ट भेज दी गई। एडमिन चेक करके फ़ैसला लेगा।", "🚩 Report sent. Admin will check and decide."),
    "✅ Report approve hui. <b>+{}</b> coins mil gaye.": ("✅ रिपोर्ट अप्रूव हुई। <b>+{}</b> कॉइन्स मिल गए।", "✅ Report approved. You received <b>+{}</b> coins."),
    "ℹ️ Bot work #{} ki submission #{} admin ne approve ki.": ("ℹ️ बॉट वर्क #{} का सबमिशन #{} एडमिन ने अप्रूव किया।", "ℹ️ Admin approved submission #{} of Bot work #{}."),
    "❌ Admin ne submission #{} ka reject sahi mana.": ("❌ एडमिन ने सबमिशन #{} का रिजेक्ट सही माना।", "❌ Admin upheld the rejection of submission #{}."),
    "ℹ️ Submission #{} reject upheld. {} coins wapas mile.": ("ℹ️ सबमिशन #{} का रिजेक्ट सही माना गया। {} कॉइन्स वापस मिले।", "ℹ️ Submission #{} rejection upheld. {} coins returned."),
    "❌ Bot work #{} reject hua: <b>{}</b>": ("❌ बॉट वर्क #{} रिजेक्ट हुआ: <b>{}</b>", "❌ Bot work #{} was rejected: <b>{}</b>"),
    "📝 <b>Reason:</b> {}": ("📝 <b>रीज़न:</b> {}", "📝 <b>Reason:</b> {}"),
    "🔁 Tumhare paas <b>ek aur mauka</b> hai. Tasks me ye bot work dobara kholo aur sahi screenshot do ({}h ke andar). Dobara reject hua to ye task tumhare liye <b>lock</b> ho jayega.": ("🔁 तुम्हारे पास <b>एक और मौका</b> है। टास्क में ये बॉट वर्क दोबारा खोलो और सही स्क्रीनशॉट दो ({} घंटे के अंदर)। दोबारा रिजेक्ट हुआ तो ये टास्क तुम्हारे लिए <b>लॉक</b> हो जाएगा।", "🔁 You have <b>one more chance</b>. Open this bot work again in Tasks and submit the correct screenshot (within {}h). If it is rejected again, this task will be <b>locked</b> for you."),
    "Agar lagta hai poster ne galat reject kiya to Report karo (Report karne par retry nahi milega).": ("अगर लगता है कि पोस्टर ने गलत रिजेक्ट किया तो Report करो (Report करने पर रीट्राई नहीं मिलेगा)।", "If you think the poster rejected it wrongly, tap Report (you won't get a retry if you report)."),
    "🔒 Ye task ab tumhare liye <b>lock</b> hai (2 try ho gaye).": ("🔒 ये टास्क अब तुम्हारे लिए <b>लॉक</b> है (2 कोशिशें हो गईं)।", "🔒 This task is now <b>locked</b> for you (2 tries used)."),
    "Agar tumne kaam sahi kiya tha to {}h ke andar Report karo.": ("अगर तुमने काम सही किया था तो {} घंटे के अंदर Report करो।", "If you did the work correctly, tap Report within {}h."),
    "Screenshot fake / edited lag raha hai": ("स्क्रीनशॉट नकली / एडिटेड लग रहा है", "Screenshot looks fake / edited"),
    "Galat screenshot diya": ("गलत स्क्रीनशॉट दिया", "Wrong screenshot given"),
    "Kaam poora nahi hua": ("काम पूरा नहीं हुआ", "Work not completed"),
    "Refer link galat hai": ("रेफ़र लिंक गलत है", "Refer link is wrong"),
    "Device verification fail / result galat": ("डिवाइस वेरिफिकेशन फेल / रिज़ल्ट गलत", "Device verification failed / wrong result"),
    "✍️ Apna reason likho": ("✍️ अपना रीज़न लिखो", "✍️ Write your own reason"),
    "⬅️ Wapas": ("⬅️ वापस", "⬅️ Back"),
    "🚩 Report": ("🚩 रिपोर्ट", "🚩 Report"),
})

# ---------------- wallet: deposit / claims / withdraw ----------------
_add({
    "❌ Payment abhi available nahi. Baad me try karo.": ("❌ पेमेंट अभी उपलब्ध नहीं है। बाद में कोशिश करो।", "❌ Payment isn't available right now. Please try later."),
    "❌ Stars payment abhi available nahi. Baad me try karo.": ("❌ स्टार्स पेमेंट अभी उपलब्ध नहीं है। बाद में कोशिश करो।", "❌ Stars payment isn't available right now. Please try later."),
    "Pehle wale payment order ko pura karo ya 12 minute ruko, phir naya banao.": ("पहले वाले पेमेंट ऑर्डर को पूरा करो या 12 मिनट रुको, फिर नया बनाओ।", "Complete your earlier payment order or wait 12 minutes, then create a new one."),
    "Bahut saare orders. Thodi der baad try karo.": ("बहुत सारे ऑर्डर हो गए। थोड़ी देर बाद कोशिश करो।", "Too many orders. Please try again in a while."),
    "Abhi bahut log payment kar rahe hain. 1 minute baad try karo.": ("अभी बहुत लोग पेमेंट कर रहे हैं। 1 मिनट बाद कोशिश करो।", "Many people are paying right now. Try again in 1 minute."),
    "Transaction ID sahi daalo (Fam app me payment detail me hota hai).": ("ट्रांज़ैक्शन ID सही डालो (Fam ऐप में पेमेंट डिटेल में होती है)।", "Enter the correct Transaction ID (it's in the payment details of the Fam app)."),
    "Amount ₹{} se ₹{} ke beech daalo.": ("अमाउंट ₹{} से ₹{} के बीच डालो।", "Enter an amount between ₹{} and ₹{}."),
    "✅ Payment mil gayi! +{} coins ad balance me add ho gaye.": ("✅ पेमेंट मिल गई! +{} कॉइन्स ऐड बैलेंस में जुड़ गए।", "✅ Payment received! +{} coins added to your ad balance."),
    "Claim bhej diya. Admin check karke credit kar dega. Mail aate hi apne aap bhi ho jayega.": ("क्लेम भेज दिया। एडमिन चेक करके क्रेडिट कर देगा। मेल आते ही अपने आप भी हो जाएगा।", "Claim sent. Admin will check and credit it. It will also happen automatically once the mail arrives."),
    "Is transaction ka claim pehle se pending hai.": ("इस ट्रांज़ैक्शन का क्लेम पहले से पेंडिंग है।", "A claim for this transaction is already pending."),
    "Bahut claims. Thodi der baad try karo.": ("बहुत सारे क्लेम। थोड़ी देर बाद कोशिश करो।", "Too many claims. Please try again in a while."),
    "Ye transaction pehle hi use ho chuka hai ya amount match nahi karta.": ("ये ट्रांज़ैक्शन पहले ही इस्तेमाल हो चुका है या अमाउंट मैच नहीं करता।", "This transaction was already used or the amount doesn't match."),
    "Min {} aur max {} coins, 100 ke multiple me daalo.": ("कम से कम {} और ज़्यादा से ज़्यादा {} कॉइन्स, 100 के गुणक में डालो।", "Enter min {} and max {} coins, in multiples of 100."),
    "Min {} coins aur 100 ke multiple me daalo.": ("कम से कम {} कॉइन्स और 100 के गुणक में डालो।", "Enter at least {} coins, in multiples of 100."),
    "Sahi premium level chuno.": ("सही प्रीमियम लेवल चुनो।", "Choose a valid premium level."),
    "Turant active karna hai ya purana premium khatam hone ke baad? Chuno.": ("तुरंत चालू करना है या पुराना प्रीमियम खत्म होने के बाद? चुनो।", "Activate now, or after your current premium ends? Please choose."),
    "{} din ka Premium Level {}": ("{} दिन का प्रीमियम लेवल {}", "{}-day Premium Level {}"),
    "🔐 Withdraw ke liye pehle device verify karo.": ("🔐 विड्रॉ के लिए पहले डिवाइस वेरिफाई करो।", "🔐 Verify your device before withdrawing."),
    "Pehle Profile me apna UPI ID set karo.": ("पहले प्रोफ़ाइल में अपना UPI ID सेट करो।", "Set your UPI ID in Profile first."),
    "⚠️ Tumne pehle channel leave kiya tha, {} coins ka hisaab baaki hai. Agle channel rewards se ye kat-ta rahega; poora kat-ne ke baad withdraw khulega.": ("⚠️ तुमने पहले चैनल छोड़ा था, {} कॉइन्स का हिसाब बाकी है। अगले चैनल रिवॉर्ड से ये कटता रहेगा; पूरा कटने के बाद विड्रॉ खुलेगा।", "⚠️ You left a channel earlier and {} coins are still owed. They will be deducted from your next channel rewards; withdrawals open once it's fully cleared."),
    "⚠️ Aaj ke {} withdraw ho chuke. Level upgrade karo ya kal (12 baje ke baad) dobara karo.": ("⚠️ आज के {} विड्रॉ हो चुके हैं। लेवल अपग्रेड करो या कल (रात 12 बजे के बाद) दोबारा करो।", "⚠️ Today's {} withdrawals are done. Upgrade your level or try again tomorrow (after 12 AM)."),
    "⚠️ Aaj ke {} withdraw ho chuke. Kal (12 baje ke baad) dobara karo.": ("⚠️ आज के {} विड्रॉ हो चुके हैं। कल (रात 12 बजे के बाद) दोबारा करो।", "⚠️ Today's {} withdrawals are done. Try again tomorrow (after 12 AM)."),
    "⚠️ Aaj ke {} withdraw ho chuke. Kal dobara karo.": ("⚠️ आज के {} विड्रॉ हो चुके हैं। कल दोबारा करो।", "⚠️ Today's {} withdrawals are done. Try again tomorrow."),
    "⚠️ Withdraw ke liye kam se kam {} task complete karo (channel join ya bot work). Abhi complete: {}.": ("⚠️ विड्रॉ के लिए कम से कम {} टास्क पूरे करो (चैनल जॉइन या बॉट वर्क)। अभी पूरे: {}।", "⚠️ Complete at least {} tasks to withdraw (channel join or bot work). Completed so far: {}."),
    "{} coins + {} tax = {} coins chahiye, balance {}. Max withdraw: {} coins.": ("{} कॉइन्स + {} टैक्स = {} कॉइन्स चाहिए, बैलेंस {}। ज़्यादा से ज़्यादा विड्रॉ: {} कॉइन्स।", "{} coins + {} tax = {} coins needed, your balance is {}. Max withdraw: {} coins."),
    "❌ Withdraw nahi ho paya. Balance aur verification check karo.": ("❌ विड्रॉ नहीं हो पाया। बैलेंस और वेरिफिकेशन चेक करो।", "❌ Withdrawal failed. Check your balance and verification."),
    "Withdraw request #{} bhej di gayi. ₹{} → {} (balance se {} + {} tax = {} coins kate). Admin approve karega to paisa aa jayega. {} ghante me process na hua to coins apne aap wapas aa jayenge.": ("विड्रॉ रिक्वेस्ट #{} भेज दी गई। ₹{} → {} (बैलेंस से {} + {} टैक्स = {} कॉइन्स कटे)। एडमिन अप्रूव करेगा तो पैसा आ जाएगा। {} घंटे में प्रोसेस न हुआ तो कॉइन्स अपने आप वापस आ जाएंगे।", "Withdraw request #{} sent. ₹{} → {} ({} + {} tax = {} coins deducted from balance). The money arrives once the admin approves. If it isn't processed within {} hours, your coins return automatically."),
    "⌛ Withdraw #{} {} ghante me process nahi hua, isliye expire ho gaya.\n<b>{}</b> coins (tax samet) tumhare balance me wapas aa gaye. Chaho to dobara withdraw karo.": ("⌛ विड्रॉ #{} {} घंटे में प्रोसेस नहीं हुआ, इसलिए एक्सपायर हो गया।\n<b>{}</b> कॉइन्स (टैक्स समेत) तुम्हारे बैलेंस में वापस आ गए। चाहो तो दोबारा विड्रॉ करो।", "⌛ Withdraw #{} wasn't processed within {} hours, so it expired.\n<b>{}</b> coins (including tax) are back in your balance. You can withdraw again."),
    "❌ Withdraw #{} reject hua, coins wapas mil gaye.": ("❌ विड्रॉ #{} रिजेक्ट हुआ, कॉइन्स वापस मिल गए।", "❌ Withdraw #{} was rejected, your coins have been returned."),
    "✅ Withdraw #{} paid: ₹{} → {} (tax {}% alag se kata)": ("✅ विड्रॉ #{} पेड: ₹{} → {} (टैक्स {}% अलग से कटा)", "✅ Withdraw #{} paid: ₹{} → {} (tax {}% deducted separately)"),
    "✅ Withdraw #{} paid: ₹{} → {}": ("✅ विड्रॉ #{} पेड: ₹{} → {}", "✅ Withdraw #{} paid: ₹{} → {}"),
    "❌ Withdraw #{} fail hua, coins wapas mil gaye.": ("❌ विड्रॉ #{} फेल हुआ, कॉइन्स वापस मिल गए।", "❌ Withdraw #{} failed, your coins have been returned."),
    "✅ <b>Deposit successful!</b>\n+{} coins ad balance me add ho gaye.": ("✅ <b>डिपॉजिट सफल!</b>\n+{} कॉइन्स ऐड बैलेंस में जुड़ गए।", "✅ <b>Deposit successful!</b>\n+{} coins added to your ad balance."),
    "❌ Tumhara deposit claim verify nahi ho paya. Galti ho to Support me batao.": ("❌ तुम्हारा डिपॉजिट क्लेम वेरिफाई नहीं हो पाया। गलती हो तो सपोर्ट में बताओ।", "❌ Your deposit claim couldn't be verified. If this is a mistake, tell us in Support."),
    "✅ <b>Premium Level {} mil gaya!</b> ({} din)": ("✅ <b>प्रीमियम लेवल {} मिल गया!</b> ({} दिन)", "✅ <b>Premium Level {} activated!</b> ({} days)"),
    "Turant chalu ho gaya 🎉": ("तुरंत चालू हो गया 🎉", "Activated immediately 🎉"),
    "Purane premium me {} din jud gaye 🎉": ("पुराने प्रीमियम में {} दिन जुड़ गए 🎉", "{} days were added to your current premium 🎉"),
    "Purana premium khatam hone ke baad apne aap chalu ho jayega ⏭️": ("पुराना प्रीमियम खत्म होने के बाद अपने आप चालू हो जाएगा ⏭️", "It will start automatically after your current premium ends ⏭️"),
    "⭐ <b>Premium Level {} chalu ho gaya!</b> ({} din). Purana premium khatam ho gaya tha.": ("⭐ <b>प्रीमियम लेवल {} चालू हो गया!</b> ({} दिन)। पुराना प्रीमियम खत्म हो गया था।", "⭐ <b>Premium Level {} is now active!</b> ({} days). Your previous premium had ended."),
    "Ye order ab valid nahi hai. App se dobara Stars payment shuru karo.": ("ये ऑर्डर अब मान्य नहीं है। ऐप से दोबारा स्टार्स पेमेंट शुरू करो।", "This order is no longer valid. Start the Stars payment again from the app."),
})

# ---------------- support / gift / upi / misc ----------------
_add({
    "Message khali hai.": ("मैसेज खाली है।", "The message is empty."),
    "🎤 Voice message sirf Premium users bhej sakte hain. Text ya photo bhejo.": ("🎤 वॉइस मैसेज सिर्फ़ प्रीमियम यूज़र भेज सकते हैं। टेक्स्ट या फोटो भेजो।", "🎤 Only Premium users can send voice messages. Send text or a photo."),
    "Bahut zyada messages ho gaye. Thodi der baad likho.": ("बहुत ज़्यादा मैसेज हो गए। थोड़ी देर बाद लिखो।", "Too many messages. Please write again in a while."),
    "Ek ghante me 5 photo/voice hi bhej sakte ho.": ("एक घंटे में सिर्फ़ 5 फोटो/वॉइस भेज सकते हो।", "You can send only 5 photos/voice messages per hour."),
    "Aaj ke liye photo/voice ki limit ho gayi. Kal bhejo ya text likho.": ("आज के लिए फोटो/वॉइस की लिमिट हो गई। कल भेजो या टेक्स्ट लिखो।", "Today's photo/voice limit is reached. Send tomorrow or write text."),
    "Sirf photo (JPG/PNG/WEBP) bhej sakte ho.": ("सिर्फ़ फोटो (JPG/PNG/WEBP) भेज सकते हो।", "You can only send photos (JPG/PNG/WEBP)."),
    "Voice sahi record nahi hui. Dobara try karo.": ("वॉइस सही रिकॉर्ड नहीं हुई। दोबारा कोशिश करो।", "Voice wasn't recorded properly. Please try again."),
    "Ek message me photo ya voice, dono nahi.": ("एक मैसेज में फोटो या वॉइस, दोनों नहीं।", "Photo or voice in one message, not both."),
    "Photo 1.5MB se chhoti bhejo.": ("फोटो 1.5MB से छोटी भेजो।", "Send a photo smaller than 1.5MB."),
    "Voice bahut lambi hai (max 60 sec).": ("वॉइस बहुत लंबी है (ज़्यादा से ज़्यादा 60 सेकंड)।", "Voice is too long (max 60 sec)."),
    "🎤 Voice message bheja gaya hai.": ("🎤 वॉइस मैसेज भेजा गया है।", "🎤 A voice message was sent."),
    "📷 Photo bheji gayi hai.": ("📷 फोटो भेजी गई है।", "📷 A photo was sent."),
    "🎧 <b>Support reply</b>\n\n{}\n\nPoori chat: App → Profile → Customer service": ("🎧 <b>सपोर्ट रिप्लाई</b>\n\n{}\n\nपूरी चैट: ऐप → प्रोफ़ाइल → कस्टमर सर्विस", "🎧 <b>Support reply</b>\n\n{}\n\nFull chat: App → Profile → Customer service"),
    "🔐 Gift code ke liye pehle device verify karo.": ("🔐 गिफ़्ट कोड के लिए पहले डिवाइस वेरिफाई करो।", "🔐 Verify your device before using a gift code."),
    "Bahut galat attempts. 1 ghante baad try karo.": ("बहुत गलत कोशिशें। 1 घंटे बाद कोशिश करो।", "Too many wrong attempts. Try again after 1 hour."),
    "Sahi gift code daalo.": ("सही गिफ़्ट कोड डालो।", "Enter a valid gift code."),
    "Gift code redeem hua! +{} coins balance me add ho gaye.": ("गिफ़्ट कोड रिडीम हुआ! +{} कॉइन्स बैलेंस में जुड़ गए।", "Gift code redeemed! +{} coins added to your balance."),
    "Ye gift code galat hai.": ("ये गिफ़्ट कोड गलत है।", "This gift code is invalid."),
    "Is gift code ki limit khatam ho gayi.": ("इस गिफ़्ट कोड की लिमिट खत्म हो गई।", "This gift code has reached its limit."),
    "Tum ye code pehle use kar chuke ho.": ("तुम ये कोड पहले इस्तेमाल कर चुके हो।", "You have already used this code."),
    "UPI save ho gaya.": ("UPI सेव हो गया।", "UPI saved."),
    "UPI ID sahi nahi hai (e.g. name@upi).": ("UPI ID सही नहीं है (जैसे name@upi)।", "UPI ID isn't valid (e.g. name@upi)."),
    "Ye UPI kisi aur account se linked hai.": ("ये UPI किसी और अकाउंट से जुड़ा है।", "This UPI is linked to another account."),
})

# ---------------- bot messages (chat) ----------------
_add({
    "🚫 Tumhara account banned hai.": ("🚫 तुम्हारा अकाउंट बैन है।", "🚫 Your account is banned."),
    "🚫 <b>App block hai</b>\nTumne ye channel leave kar diya hai:\n{}\n\nDobara join karo, phir app me <b>Re-check</b> dabao.": ("🚫 <b>ऐप ब्लॉक है</b>\nतुमने ये चैनल छोड़ दिए हैं:\n{}\n\nदोबारा जॉइन करो, फिर ऐप में <b>Re-check</b> दबाओ।", "🚫 <b>App is blocked</b>\nYou have left these channels:\n{}\n\nJoin them again, then tap <b>Re-check</b> in the app."),
    "➕ Join {}": ("➕ जॉइन करो: {}", "➕ Join {}"),
    "🚀 Open App": ("🚀 ऐप खोलो", "🚀 Open App"),
    "🔐 Verify Device": ("🔐 डिवाइस वेरिफाई करो", "🔐 Verify Device"),
    "👋 <b>{} me welcome!</b>\n\n🔐 Shuru karne se pehle <b>Device Verification</b> zaroori hai (ek device = ek account).\nNeeche button dabao, verification page khulega. Pass hone par yahin bot par wapas aa jaoge, phir app khulega.": ("👋 <b>{} में स्वागत है!</b>\n\n🔐 शुरू करने से पहले <b>डिवाइस वेरिफिकेशन</b> ज़रूरी है (एक डिवाइस = एक अकाउंट)।\nनीचे बटन दबाओ, वेरिफिकेशन पेज खुलेगा। पास होने पर यहीं बॉट पर वापस आ जाओगे, फिर ऐप खुलेगा।", "👋 <b>Welcome to {}!</b>\n\n🔐 <b>Device Verification</b> is required before you start (one device = one account).\nTap the button below to open the verification page. Once you pass, you'll return here to the bot and then the app opens."),
    "✅ Tumhara account verify ho gaya hai. App kholo 👇": ("✅ तुम्हारा अकाउंट वेरिफाई हो गया है। ऐप खोलो 👇", "✅ Your account is verified. Open the app 👇"),
    "🔐 Tumhara device reset ho gaya. App kholo aur dobara verify karo.": ("🔐 तुम्हारा डिवाइस रीसेट हो गया। ऐप खोलो और दोबारा वेरिफाई करो।", "🔐 Your device was reset. Open the app and verify again."),
    "🚫 Tumne channel leave kiya. Coins cut ho gaye, tasks block hain jab tak rejoin na karo.": ("🚫 तुमने चैनल छोड़ा। कॉइन्स कट गए, रीजॉइन करने तक टास्क ब्लॉक हैं।", "🚫 You left a channel. Coins were deducted and tasks are blocked until you rejoin."),
    "🚫 Tumne channel leave kiya. {} coins cut ho gaye aur tasks block hain jab tak dobara join na karo. Dobara join karne par sirf {}% coins milenge ({}h hold me).": ("🚫 तुमने चैनल छोड़ा। {} कॉइन्स कट गए और दोबारा जॉइन करने तक टास्क ब्लॉक हैं। दोबारा जॉइन करने पर सिर्फ़ {}% कॉइन्स मिलेंगे ({} घंटे होल्ड में)।", "🚫 You left a channel. {} coins were deducted and tasks are blocked until you rejoin. After rejoining you'll get only {}% of the coins ({}h on hold)."),
    "🚫 Channel leave kiya, coins cut. Rejoin karo.": ("🚫 चैनल छोड़ा, कॉइन्स कट गए। रीजॉइन करो।", "🚫 You left a channel, coins deducted. Please rejoin."),
    "✅ Rejoin ho gaya. <b>{}</b> coins ({}%) {}h hold me mile. Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.": ("✅ रीजॉइन हो गया। <b>{}</b> कॉइन्स ({}%) {} घंटे होल्ड में मिले। अगर कोई और चैनल छोड़ा है तो उसे भी रीजॉइन करो।", "✅ Rejoined. You got <b>{}</b> coins ({}%) on {}h hold. If you left any other channel, rejoin it too."),
    "✅ Rejoin ho gaya. (Is channel ka reward ek baar hi milta hai.) Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.": ("✅ रीजॉइन हो गया। (इस चैनल का रिवॉर्ड एक ही बार मिलता है।) अगर कोई और चैनल छोड़ा है तो उसे भी रीजॉइन करो।", "✅ Rejoined. (The reward for this channel is given only once.) If you left any other channel, rejoin it too."),
    "✅ {} coins released! Ab withdraw kar sakte ho.": ("✅ {} कॉइन्स रिलीज़ हो गए! अब विड्रॉ कर सकते हो।", "✅ {} coins released! You can withdraw now."),
    "🎉 <b>Refer complete!</b> Tumhare dost ne apne task complete kar liye. <b>+{}</b> coins ad balance me add (ye sirf task banane me use ho sakte hain).": ("🎉 <b>रेफ़र पूरा!</b> तुम्हारे दोस्त ने अपने टास्क पूरे कर लिए। <b>+{}</b> कॉइन्स ऐड बैलेंस में जुड़े (ये सिर्फ़ टास्क बनाने में इस्तेमाल हो सकते हैं)।", "🎉 <b>Referral complete!</b> Your friend completed their tasks. <b>+{}</b> coins added to your ad balance (usable only for creating tasks)."),
    "📢 <b>{} naya channel task</b>: join karo aur coins kamao!": ("📢 <b>{} नए चैनल टास्क</b>: जॉइन करो और कॉइन्स कमाओ!", "📢 <b>{} new channel tasks</b>: join and earn coins!"),
    "📢 <b>Naya channel task</b>: {}\nJoin karo, {} coins kamao!": ("📢 <b>नया चैनल टास्क</b>: {}\nजॉइन करो, {} कॉइन्स कमाओ!", "📢 <b>New channel task</b>: {}\nJoin and earn {} coins!"),
    "🤖 <b>{} naya Bot Work</b> add hua!": ("🤖 <b>{} नए बॉट वर्क</b> जुड़े!", "🤖 <b>{} new Bot Works</b> added!"),
    "🤖 <b>Naya Bot Work</b>: {}\nReward: {} coins": ("🤖 <b>नया बॉट वर्क</b>: {}\nरिवॉर्ड: {} कॉइन्स", "🤖 <b>New Bot Work</b>: {}\nReward: {} coins"),
    "👇 App kholo": ("👇 ऐप खोलो", "👇 Open the app"),
    "Cancel hua. Owner ko {} coins refund.": ("कैंसल हो गया। ओनर को {} कॉइन्स रिफ़ंड हुए।", "Cancelled. {} coins refunded to the owner."),
    "{} din ka Premium Level {}": ("{} दिन का प्रीमियम लेवल {}", "{}-day Premium Level {}"),
    "Already verified": ("पहले से वेरिफ़ाइड", "Already verified"),
    "Not allowed": ("अनुमति नहीं", "Not allowed"),
    "Galat action": ("गलत एक्शन", "Invalid action"),
    "User nahi mila.": ("यूज़र नहीं मिला।", "User not found."),
    "🔔 Notification ON": ("🔔 नोटिफ़िकेशन ON", "🔔 Notifications ON"),
    "🔕 Notification OFF": ("🔕 नोटिफ़िकेशन OFF", "🔕 Notifications OFF"),
    "Ab support reply app ke andar hota hai: Profile → Support inbox.": ("अब सपोर्ट रिप्लाई ऐप के अंदर होता है: प्रोफ़ाइल → कस्टमर सर्विस।", "Support replies now happen inside the app: Profile → Customer service."),
    "Google Play code request #{} bhej di gayi. ₹{} ka code (balance se {} + {} tax = {} coins kate). Admin code bhejega to wo bot me aayega aur Wallet → Gift Codes me bhi dikhega. {} ghante me process na hua to coins apne aap wapas aa jayenge.": ("Google Play कोड रिक्वेस्ट #{} भेज दी गई। ₹{} का कोड (बैलेंस से {} + {} टैक्स = {} कॉइन्स कटे)। एडमिन कोड भेजेगा तो वो बॉट में आएगा और वॉलेट → Gift Codes में भी दिखेगा। {} घंटे में प्रोसेस न हुआ तो कॉइन्स अपने आप वापस आ जाएँगे।", "Google Play code request #{} sent. Code worth ₹{} ({} + {} tax = {} coins deducted from your balance). When the admin sends the code it will arrive in this bot and also show under Wallet → Gift Codes. If it isn't processed within {} hours, your coins are refunded automatically."),
    "🎁 <b>Google Play code ready!</b>\nWithdraw #{}: ₹{}\nCode: <code>{}</code>\nPlay Store → Profile → Payments & subscriptions → Redeem gift code me daalo. Ye code Wallet → Gift Codes me bhi save hai.": ("🎁 <b>Google Play कोड तैयार!</b>\nविड्रॉ #{}: ₹{}\nकोड: <code>{}</code>\nPlay Store → Profile → Payments & subscriptions → Redeem gift code में डालो। ये कोड वॉलेट → Gift Codes में भी सेव है।", "🎁 <b>Your Google Play code is ready!</b>\nWithdraw #{}: ₹{}\nCode: <code>{}</code>\nEnter it in Play Store → Profile → Payments & subscriptions → Redeem gift code. This code is also saved under Wallet → Gift Codes."),
    "Google Play code ₹{} ke multiple me hota hai ({} coins ke multiple me daalo, jaise {}, {}, {}).": ("Google Play कोड ₹{} के मल्टीपल में होता है ({} कॉइन के मल्टीपल में डालो, जैसे {}, {}, {})।", "Google Play codes come in multiples of ₹{} (enter a multiple of {} coins, e.g. {}, {}, {})."),
    "Bot Work banana Premium Level 1 se khulta hai. Premium lo.": ("बॉट वर्क बनाना प्रीमियम लेवल 1 से खुलता है। प्रीमियम लो।", "Creating Bot Work unlocks with Premium Level 1. Get Premium."),
    "📢 Pehle hamara channel join karo.": ("📢 पहले हमारा चैनल जॉइन करो।", "📢 Please join our channel first."),
    "✅ Verify ho gaya! Welcome.": ("✅ वेरिफाई हो गया! वेलकम।", "✅ Verified! Welcome."),
    "❌ Abhi channel join nahi dikha. Join karke thodi der baad Verify dabao.": ("❌ अभी चैनल जॉइन नहीं दिखा। जॉइन करके थोड़ी देर बाद वेरिफाई दबाओ।", "❌ We can't see you in the channel yet. Join it, then tap Verify again in a moment."),
    "🔥 <b>Streak Day {} complete!</b> +{} coins.": ("🔥 <b>स्ट्रीक डे {} पूरा!</b> +{} कॉइन्स।", "🔥 <b>Streak Day {} complete!</b> +{} coins."),
    "❌ USDT payment abhi available nahi. Baad me try karo.": ("❌ USDT पेमेंट अभी उपलब्ध नहीं है। बाद में कोशिश करो।", "❌ USDT payment isn't available right now. Try again later."),
    "Amount {} se {} USDT ke beech daalo.": ("अमाउंट {} से {} USDT के बीच डालो।", "Enter an amount between {} and {} USDT."),
    "Pehle wale USDT orders pure karo ya thodi der ruko, phir naya banao.": ("पहले वाले USDT ऑर्डर पूरे करो या थोड़ी देर रुको, फिर नया बनाओ।", "Finish your earlier USDT orders or wait a bit, then create a new one."),
    "Is amount par payment nahi ban paya. Minimum {} USDT se upar try karo.": ("इस अमाउंट पर पेमेंट नहीं बन पाया। {} USDT से ऊपर कोशिश करो।", "Couldn't create a payment for this amount. Try above {} USDT."),
    "❌ USDT payment abhi nahi ban paya. Thodi der baad try karo.": ("❌ USDT पेमेंट अभी नहीं बन पाया। थोड़ी देर बाद कोशिश करो।", "❌ Couldn't create the USDT payment. Try again shortly."),
    "❌ USDT withdraw abhi available nahi.": ("❌ USDT विड्रॉ अभी उपलब्ध नहीं है।", "❌ USDT withdraw isn't available right now."),
    "BEP20 (BSC) wallet address sahi daalo: 0x se shuru, 42 characters.": ("BEP20 (BSC) वॉलेट एड्रेस सही डालो: 0x से शुरू, 42 अक्षर।", "Enter a valid BEP20 (BSC) wallet address: starts with 0x, 42 characters."),
    "USDT withdraw request #{} bhej di gayi. {} USDT (BEP20) → {}…{} (balance se {} + {} tax = {} coins kate). Admin bhejega to Transaction ID (TxID) bot me aayegi aur Wallet me bhi dikhegi. {} ghante me process na hua to coins apne aap wapas aa jayenge.": ("USDT विड्रॉ रिक्वेस्ट #{} भेज दी गई। {} USDT (BEP20) → {}…{} (बैलेंस से {} + {} टैक्स = {} कॉइन्स कटे)। एडमिन भेजेगा तो ट्रांज़ैक्शन ID (TxID) बॉट में आएगी और वॉलेट में भी दिखेगी। {} घंटे में प्रोसेस न हुआ तो कॉइन्स अपने आप वापस आ जाएंगे।", "USDT withdraw request #{} sent. {} USDT (BEP20) → {}…{} ({} + {} tax = {} coins deducted from balance). Once the admin sends it, the Transaction ID (TxID) will arrive in the bot and show in your Wallet. If it isn't processed within {} hours, your coins return automatically."),
    "⚠️ Tumne USDT kam bheje. Order poora nahi hua. Baaki amount usi address par bhejo ya Support se contact karo.": ("⚠️ तुमने USDT कम भेजे। ऑर्डर पूरा नहीं हुआ। बाकी अमाउंट उसी एड्रेस पर भेजो या सपोर्ट से संपर्क करो।", "⚠️ You sent less USDT than required. The order isn't complete. Send the remaining amount to the same address or contact Support."),
    "✅ <b>USDT withdraw paid!</b>\nWithdraw #{}: <b>{} USDT</b> (BEP20) → <code>{}</code>\nTxID: <code>{}</code>\n<a href=\"https://bscscan.com/tx/{}\">BscScan par dekho</a>\nYe TxID Wallet → History me bhi save hai.": ("✅ <b>USDT विड्रॉ पेड!</b>\nविड्रॉ #{}: <b>{} USDT</b> (BEP20) → <code>{}</code>\nTxID: <code>{}</code>\n<a href=\"https://bscscan.com/tx/{}\">BscScan पर देखो</a>\nयह TxID वॉलेट → हिस्ट्री में भी सेव है।", "✅ <b>USDT withdraw paid!</b>\nWithdraw #{}: <b>{} USDT</b> (BEP20) → <code>{}</code>\nTxID: <code>{}</code>\n<a href=\"https://bscscan.com/tx/{}\">View on BscScan</a>\nThis TxID is also saved in Wallet → History."),
    "🏆 <b>Milestone bonus!</b> {} refers complete hone par <b>+{}</b> extra coins ad balance me add.": ("🏆 <b>माइलस्टोन बोनस!</b> {} रेफ़र पूरे होने पर <b>+{}</b> एक्स्ट्रा कॉइन्स ऐड बैलेंस में जुड़ गए।", "🏆 <b>Milestone bonus!</b> For completing {} referrals you got <b>+{}</b> extra coins in your ad balance."),
    "Amazon voucher ₹{} ke multiple me hota hai ({} coins ke multiple me daalo, jaise {}, {}, {}).": ("Amazon वाउचर ₹{} के मल्टिपल में होता है ({} कॉइन्स के मल्टिपल में डालो, जैसे {}, {}, {})।", "Amazon vouchers come in multiples of ₹{} (enter a multiple of {} coins, e.g. {}, {}, {})."),
    "Amazon voucher request #{} bhej di gayi. ₹{} ka voucher (balance se {} + {} tax = {} coins kate). Admin voucher code bhejega to wo bot me aayega aur Wallet → Gift Codes me bhi dikhega. {} ghante me process na hua to coins apne aap wapas aa jayenge.": ("Amazon वाउचर रिक्वेस्ट #{} भेज दी गई। ₹{} का वाउचर (बैलेंस से {} + {} टैक्स = {} कॉइन्स कटे)। एडमिन वाउचर कोड भेजेगा तो वो बॉट में आएगा और वॉलेट → Gift Codes में भी दिखेगा। {} घंटे में प्रोसेस न हुआ तो कॉइन्स अपने आप वापस आ जाएंगे।", "Amazon voucher request #{} sent. ₹{} voucher ({} + {} tax = {} coins deducted from balance). Once the admin sends the voucher code it arrives in the bot and shows under Wallet → Gift Codes. If it isn't processed within {} hours, your coins return automatically."),
    "🛒 <b>Amazon voucher ready!</b>\nWithdraw #{}: ₹{}\nCode: <code>{}</code>\nAmazon app → Account → Gift Cards → Redeem a Gift Card me daalo. Ye code Wallet → Gift Codes me bhi save hai.": ("🛒 <b>Amazon वाउचर तैयार!</b>\nविड्रॉ #{}: ₹{}\nकोड: <code>{}</code>\nAmazon ऐप → Account → Gift Cards → Redeem a Gift Card में डालो। यह कोड वॉलेट → Gift Codes में भी सेव है।", "🛒 <b>Amazon voucher ready!</b>\nWithdraw #{}: ₹{}\nCode: <code>{}</code>\nAmazon app → Account → Gift Cards → Redeem a Gift Card and enter it. This code is also saved under Wallet → Gift Codes."),
"🗑 History saaf ho gayi.": ("🗑 हिस्ट्री साफ़ हो गई।", "🗑 History cleared."),
"Ye task tumhara nahi hai (sirf task ka owner Done/Reject kar sakta hai).": ("यह टास्क तुम्हारा नहीं है (सिर्फ़ टास्क का ओनर Done/Reject कर सकता है)।", "This task isn't yours (only the task owner can tap Done/Reject)."),
"Ye submission pehle hi process ho chuki hai.": ("यह सबमिशन पहले ही प्रोसेस हो चुका है।", "This submission was already processed."),
})

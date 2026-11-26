# Tribes API contract

GET `/api/tribes/state?season_id=123` (omit for current), GET `/api/tribes/seasons` => array of `{id,status,starts_at,ends_at}` newest first.
POST `/api/tribes/actions` authenticated `{season_id,request_id:UUID,action,...fields}`. All POSTs return fresh state below, retries reuse the UUID and exact payload. Errors use the app’s standard `[{code, message}]` shape (some authentication errors may use `{detail}`); 409 for reused UUID with different payload. IDs are numbers except player dictionary keys. Timestamps ISO UTC.

State:

```
{
 season:{id,status:'recruiting'|'active'|'finished',starts_at,ends_at}, server_time,
 catalog:{land:{forest:{resource:'timber',price:40},...},recipes:{lumber:{inputs:{timber:2},seconds:120,facility:null},...},units:{infantry:{damage:10,range:1},...},defenses:{barricade:30,stone_wall:100},buildings:{...},items:string[],trade_items:string[],market_items:string[],work_order_items:string[],max_members:8,queue_seconds:86400,gather_capacity:5,unit_capacity:100,building_capacity:3,currency:'TNB',gather_rate:10},
 viewer: null | {id,username,tribe_id:number|null,wallet_balance:number,inventory:{item:quantity},production:{item:quantity},experience:{item:quantity}},
 tribes:[{id,name,emblem,color,description,motto,founder_id,members:[{id,username}], treasury:number|null,inventory:object|null,applications:[{id,username}] (own founder only),invites:[{id,username}] (own founder only)}],
 invitations:[{tribe_id,name}], applications:[{tribe_id,name}],
 plots:[{id,x,y,terrain,tribe_id:number|null,price,buildings:string[]}],
 jobs:[{id,user_id,tribe_id,kind:'gather'|'craft'|'build',item,quantity,completed,plot_id,start_at,end_at,status:'queued'|'working'|'completed'|'cancelled',source:'personal'|'tribe',destination:'personal'|'tribe'}],
 units:[{id,tribe_id,controller_id,item,quantity,plot_id,target_id:number|null (omitted for rivals),valid_target_ids:number[]}],
 listings:[{id,kind:'sell'|'buy',item,quantity,price,user_id:null|number,tribe_id:null|number,account:'personal'|'tribe'}],
 messages:[{id,from_tribe_id,to_tribe_id,user_id,username,text,created_at}],
 work_orders:[{id,tribe_id,title,item,quantity,contributed,description,status:'open'|'completed'|'cancelled'}],
 activity:[{id,tribe_id,user_id,username,text,created_at}],
 battle:null|{standings:[{tribe_id,name,outgoing,incoming,raw_incoming,blocked,defense,score,rank,attacks:[]}],attacks:[{unit_id,tribe_id,target_id,controller_id,raw_damage,effective_damage}]}
}
```
`jobs` contains own tribe full jobs plus rivals military production only. `messages` is private tribe chat and correspondence involving own tribe. `work_orders` and activity own tribe only. Public finished battle/targets; private inventories/messages stay private after season. Treasury is actual TNB: no grants. End-of-season treasury divided equally among locked members, remainder to lowest IDs; buy order escrows refunded. Real app balances persist. System land/opening-stock payments remain permanently recorded as season revenue.

Actions (flat fields besides common envelope):

- create_tribe: name, emblem (emoji/text max8), color (#rrggbb), description, motto
- update_tribe: name, emblem,color,description,motto (founder recruiting only)
- apply: tribe_id
- invite: username (founder own tribe)
- accept_invite: tribe_id
- accept_application: user_id (founder own tribe)
- remove_member: user_id (founder cannot remove self)
- leave: no fields (founder must be only member; removes empty team)
- treasury_deposit / treasury_withdraw: amount
- purchase_land: plot_id (treasury pays)
- queue: kind, plot_id, item (craft/build), quantity (craft; build=1), hours (gather 1..12), source (personal|tribe, default tribe), destination (personal|tribe, default tribe). Optional target_id preassigns military production targets; new completed units inherit it. All non-gather inputs reserved at queue time. Facilities required when queuing. Up to 24h future worker time. Buildings/units/defenses placed on plot; rest deposited destination inventory. Gathering progressive hourly fractions, craft per completed item. Materials for unfinished items returned on cancellation.
- cancel_job: job_id (own worker)
- transfer_items: item,quantity,source (personal|tribe), destination (personal|tribe), recipient_user_id (for personal, default self), recipient_tribe_id (for tribe, default own). Personal recipient must be own teammate. Own personal <-> tribe and tribe -> other tribe supported.
- transfer_tnb: amount,recipient_tribe_id (from own treasury)
- create_listing: kind (sell|buy),item,quantity,price,account (personal|tribe). Buy escrow TNB; sell escrow goods.
- fill_listing: listing_id,quantity,account (personal|tribe). For sell pays & receives goods; for buy supplies goods & receives TNB. Cannot fill own listing.
- cancel_listing: listing_id (creator; escrow returned). Military sale: create_listing accepts infantry/catapult/trebuchet/barricade/stone_wall with unit_id and quantity (current controller only, sell only). Military fill_listing requires plot_id owned by buyer; control passes to buyer and target clears. Listed units reserve original plot capacity until sold/cancelled. catalog.market_items includes these units in addition to trade_items.
- deploy: unit_id,plot_id,target_id (null clears; controller only)
- transfer_unit: unit_id,recipient_user_id,plot_id (recipient roster owns destination; clears target, entire batch)
- message: text,to_tribe_id (own tribe for private chat; another tribe for diplomatic mail)
- create_work_order: title,description,item,quantity. catalog.work_order_items includes military/defenses/buildings, whose progress is tracked automatically from subsequent tribe production. Materials/tools use explicit stockpile contributions.
- cancel_work_order: work_order_id (any member; returns partial project escrow to warehouse)
- contribute_work_order: work_order_id,quantity,source (personal|tribe; goods reserved to project and count toward completed contribution)

MVP crafting entries include all material refinements, tools, infantry/catapult/trebuchet, barricade/stone_wall, lumber_camp/mine/farm/quarry_building/furnace/workshop. Resource specialization +1/hour per100 produced up to +5, equipment pickaxe/axe +5/hour (held personal or warehouse), matching building +10/hour; base10/hour. Buildings max3 per plot, military max100 units per plot; gathering max5 simultaneous workers.

Activity history: GET `/api/tribes/activity?season_id=123&before=456` authenticated own historical tribe only, returns `{results: Activity[], next_before: number|null}` latest100 descending. Omit before for first page; use final state.activity ID to load older dashboard records. GET `/api/tribes/seasons?before=123` returns older100 seasons for permanent history browsing.

Correspondence history: GET `/api/tribes/messages?season_id=123&before=456` returns `{results: Message[], next_before: number|null}` with the latest100 accessible messages in descending ID order. Only the viewer’s tribe as sender or recipient may read the thread, even after the season ends. `state.messages` remains chronological (ascending) latest200; use its minimum ID to retrieve older messages.

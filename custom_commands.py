from helper_functions import *


async def edit_boost(ctx, boost_obj, boost_msg, boost_id, client, timeout):
    msg = None
    orig_boost_status = boost_obj.status
    boost_obj.status = 'editing'
    fixed_args = {'client': client, 'channel': ctx.channel, 'author': ctx.message.author, 'timeout': timeout, 'on_query_fail_msg': f'Failed to respond in {timeout}s, cancelling edit.'}
    boost_msg = await boost_msg.edit(embed=boost_obj.embed())

    main_msg = await query_user(query='What property to edit? pot/key/advertiser/boosts number/armor stack/realm/w char/note', **fixed_args)
    if main_msg is None:
        boost_obj.status = 'open'
        return await boost_msg.edit(embed=boost_obj.embed())

    if main_msg.content in ('pot', 'key', 'advertiser', 'boosts number', 'armor stack', 'realm', 'w char', 'note'):

        msg = None
        if main_msg.content == 'pot':
            new_pot = None
            while not new_pot:
                msg = await query_user(query='New pot amount?', **fixed_args)
                if msg is None:
                    break

                new_pot = gold_str2int(msg.content)
                if new_pot > 2 ** 31 - 1:
                    await ctx.channel.send('Only amounts between -2147483647 and 2147483647 are accepted.')
                    continue

                boost_obj.pot = new_pot

        elif main_msg.content == 'key':
            while not msg:
                msg = await query_user(query='New key?', **fixed_args)
                if not msg:
                    break
                else:
                    boost_obj.key = msg.content

        elif main_msg.content == 'advertiser':
            while not msg:
                msg = await query_user(query='New advertiser?', **fixed_args)
                if not msg:
                    break
                else:
                    if is_mention(msg.content):
                        new_advertiser = ctx.guild.get_member(mention2id(msg.content))
                        if new_advertiser:
                            boost_obj.advertiser_mention = new_advertiser.mention
                            boost_obj.advertiser_display_name = new_advertiser.display_name
                        else:
                            msg = None
                    else:
                        msg = None

        elif main_msg.content == 'boosts number':
            while msg is None:
                msg = await query_user(query='New number of boosts?', **fixed_args)
                if msg is None:
                    break

                try:
                    num_boosts = int(msg.content)
                except:
                    await ctx.channel.send(f'{msg.content} is not a number!')
                    msg = None
                    continue

                boost_obj.boosts_number = num_boosts

        elif main_msg.content == 'armor stack':
            while msg is None:
                msg = await query_user(query='New armor stack?', **fixed_args)
                if msg is None:
                    break

                if msg.content == 'no':
                    boost_obj.armor_stack = msg.content

                if is_mention(msg.content):
                    role = ctx.message.guild.get_role(mention2id(msg.content))
                    if role is not None and role.name in ('Cloth', 'Leather', 'Mail', 'Plate'):
                        boost_obj.change_armor_stack(role)

        elif main_msg.content == 'realm':
            while not msg:
                msg = await query_user(query='New realm name?', **fixed_args)
                if not msg:
                    break

                try:
                    realm_name = constants.is_valid_realm(msg.content, True)
                except BadArgument as e:
                    await ctx.channel.send(e)
                    continue

                boost_obj.realm_name = realm_name

        elif main_msg.content == 'w char':
            while not msg:
                msg = await query_user(query='New character to whisper?', **fixed_args)
                if not msg:
                    break
                else:
                    boost_obj.character_to_whisper = msg.content

        elif main_msg.content == 'note':
            while not msg:
                msg = await query_user(query='New note?', **fixed_args)
                if not msg:
                    break
                else:
                    boost_obj.note = msg.content

        else:
            await ctx.channel.send('Unknown value to edit!')

    else:
        await ctx.channel.send('Unknown value to edit!')

    boost_obj.status = orig_boost_status
    boost_msg = await boost_msg.edit(embed=boost_obj.embed())
    if msg is not None:
        await ctx.message.channel.send(f'Boost {boost_id} edited.')
        return boost_msg

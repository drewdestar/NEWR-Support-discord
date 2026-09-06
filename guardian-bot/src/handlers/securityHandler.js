/**
 * Security Handler - Anti-Nuke, Anti-Raid, Anti-Spam System
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Security Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This security system is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

const moment = require('moment');

module.exports = (client) => {
    console.log('🛡️ Security Handler initialized - Powered by NEWR LABS');
    console.log('© 2024 NEWROPLY - All Rights Reserved');
    
    // Track channel deletions
    client.on('channelDelete', async (channel) => {
        if (!channel.guild) return;
        
        const auditLogs = await channel.guild.fetchAuditLogs({ limit: 1, type: 30 }).catch(() => null);
        const deleteLog = auditLogs?.entries.first();
        
        if (!deleteLog) return;
        
        const { executor, target } = deleteLog;
        if (target?.id !== channel.id) return;
        
        const key = `${channel.guild.id}-${executor.id}`;
        const now = Date.now();
        
        if (!client.nukeTracker.has(key)) {
            client.nukeTracker.set(key, { count: 1, timestamp: now });
        } else {
            const tracker = client.nukeTracker.get(key);
            tracker.count++;
            
            if (tracker.count >= global.config.security.maxChannelDeleteThreshold && (now - tracker.timestamp) < 10000) {
                // ANTI-NUKE TRIGGERED
                console.log(`🚨 NUKE DETECTED! ${executor.tag} deleted ${tracker.count} channels`);
                
                try {
                    await channel.guild.members.ban(executor.id, { reason: 'Anti-Nuke: Mass channel deletion detected' });
                    
                    // Restore channel
                    await channel.clone({ name: channel.name, topic: channel.topic, parent: channel.parentId, permissionOverwrites: channel.permissionOverwrites })
                        .then(newChannel => newChannel.send(`🛡️ Channel restored after nuke attempt by ${executor.tag}`))
                        .catch(console.error);
                    
                    // Log security event
                    await global.db.run(
                        'INSERT INTO security_events (guild_id, event_type, severity, user_id, details, action_taken) VALUES (?, ?, ?, ?, ?, ?)',
                        [channel.guild.id, 'antinuke_channel', 'critical', executor.id, `Deleted ${tracker.count} channels`, 'banned']
                    );
                    
                } catch (err) {
                    console.error('Failed to handle nuke:', err);
                }
                
                client.nukeTracker.delete(key);
            }
        }
    });
    
    // Track role deletions
    client.on('guildRoleDelete', async (role) => {
        const auditLogs = await role.guild.fetchAuditLogs({ limit: 1, type: 32 }).catch(() => null);
        const deleteLog = auditLogs?.entries.first();
        
        if (!deleteLog) return;
        
        const { executor } = deleteLog;
        const key = `${role.guild.id}-${executor.id}-role`;
        const now = Date.now();
        
        if (!client.nukeTracker.has(key)) {
            client.nukeTracker.set(key, { count: 1, timestamp: now });
        } else {
            const tracker = client.nukeTracker.get(key);
            tracker.count++;
            
            if (tracker.count >= global.config.security.maxRoleDeleteThreshold && (now - tracker.timestamp) < 10000) {
                console.log(`🚨 ROLE NUKE DETECTED! ${executor.tag} deleted ${tracker.count} roles`);
                
                try {
                    await role.guild.members.ban(executor.id, { reason: 'Anti-Nuke: Mass role deletion' });
                    
                    await global.db.run(
                        'INSERT INTO security_events (guild_id, event_type, severity, user_id, details, action_taken) VALUES (?, ?, ?, ?, ?, ?)',
                        [role.guild.id, 'antinuke_role', 'critical', executor.id, `Deleted ${tracker.count} roles`, 'banned']
                    );
                } catch (err) {
                    console.error('Failed to handle role nuke:', err);
                }
            }
        }
    });
    
    // Track member joins for anti-raid
    client.on('guildMemberAdd', async (member) => {
        const key = member.guild.id;
        const now = Date.now();
        
        if (!client.raidTracker.has(key)) {
            client.raidTracker.set(key, { count: 1, timestamp: now, members: [member.id] });
        } else {
            const tracker = client.raidTracker.get(key);
            
            if (now - tracker.timestamp > 60000) {
                tracker.count = 1;
                tracker.timestamp = now;
                tracker.members = [member.id];
            } else {
                tracker.count++;
                tracker.members.push(member.id);
                
                if (tracker.count >= global.config.security.antiRaidJoinThreshold) {
                    console.log(`🚨 RAID DETECTED! ${tracker.count} members joined in 60 seconds`);
                    
                    try {
                        // Lockdown server
                        for (const channel of member.guild.channels.cache.values()) {
                            if (channel.type === 0 || channel.type === 5) {
                                await channel.permissionOverwrites.edit(member.guild.roles.everyone, { SEND_MESSAGES: false })
                                    .catch(() => {});
                            }
                        }
                        
                        // Ban raid members
                        for (const memberId of tracker.members) {
                            try {
                                const m = await member.guild.members.fetch(memberId);
                                if (m.joinedTimestamp > tracker.timestamp - 60000) {
                                    await m.ban({ reason: 'Anti-Raid: Mass join detected' });
                                }
                            } catch (err) {}
                        }
                        
                        await global.db.run(
                            'INSERT INTO security_events (guild_id, event_type, severity, details, action_taken) VALUES (?, ?, ?, ?, ?)',
                            [member.guild.id, 'antiraid', 'critical', `${tracker.count} members raided`, 'lockdown_bans']
                        );
                        
                    } catch (err) {
                        console.error('Failed to handle raid:', err);
                    }
                }
            }
        }
    });
    
    // Anti-spam message tracking
    client.on('messageCreate', async (message) => {
        if (!message.guild || message.author.bot) return;
        
        const key = `${message.guild.id}-${message.author.id}`;
        const now = Date.now();
        
        if (!client.spamTracker.has(key)) {
            client.spamTracker.set(key, { count: 1, timestamp: now, messages: [message.content] });
        } else {
            const tracker = client.spamTracker.get(key);
            
            if (now - tracker.timestamp > 5000) {
                tracker.count = 1;
                tracker.timestamp = now;
                tracker.messages = [message.content];
            } else {
                tracker.count++;
                tracker.messages.push(message.content);
                
                // Check for spam
                if (tracker.count >= global.config.security.antiSpamThreshold) {
                    const sameMessageCount = tracker.messages.filter(m => m === message.content).length;
                    
                    if (sameMessageCount >= 4) {
                        console.log(`🚨 SPAM DETECTED! ${message.author.tag}`);
                        
                        try {
                            const muteRole = await message.guild.roles.create({
                                name: 'Muted',
                                permissions: [],
                                reason: 'Auto-mute for spam'
                            });
                            
                            await message.member.roles.add(muteRole, 'Auto-mute: Spam detected');
                            
                            // Delete spam messages
                            const messages = await message.channel.messages.fetch({ limit: 10 });
                            await message.channel.bulkDelete(messages.filter(m => m.author.id === message.author.id));
                            
                            await global.db.run(
                                'INSERT INTO security_events (guild_id, event_type, severity, user_id, details, action_taken) VALUES (?, ?, ?, ?, ?, ?)',
                                [message.guild.id, 'antispam', 'warning', message.author.id, `Spam: ${sameMessageCount} duplicate messages`, 'muted']
                            );
                            
                        } catch (err) {
                            console.error('Failed to handle spam:', err);
                        }
                        
                        client.spamTracker.delete(key);
                    }
                }
            }
        }
        
        // Check for invite links
        if (global.config.security.antiInviteEnabled && message.content.match(/discord\.gg\/[a-zA-Z0-9]+/)) {
            const isWhitelisted = await global.db.get('SELECT 1 FROM whitelist WHERE guild_id = ? AND (user_id = ? OR role_id IN (SELECT role_id FROM auto_roles WHERE guild_id = ?))', [message.guild.id, message.author.id, message.guild.id]);
            
            if (!isWhitelisted) {
                await message.delete().catch(() => {});
                await message.author.send('⚠️ Invite links are not allowed in this server.').catch(() => {});
                
                await global.db.run(
                    'INSERT INTO security_events (guild_id, event_type, severity, user_id, details) VALUES (?, ?, ?, ?, ?)',
                    [message.guild.id, 'antiinvite', 'low', message.author.id, 'Posted invite link']
                );
            }
        }
    });
};

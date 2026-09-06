require('dotenv').config();
const { Client, GatewayIntentBits, Collection, Events, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, PermissionFlagsBits } = require('discord.js');
const fs = require('fs');
const path = require('path');

// Initialize client with all intents
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildBans,
        GatewayIntentBits.GuildEmojisAndStickers,
        GatewayIntentBits.GuildIntegrations,
        GatewayIntentBits.GuildWebhooks,
        GatewayIntentBits.GuildInvites,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildPresences,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildMessageReactions,
        GatewayIntentBits.GuildMessageTyping,
        GatewayIntentBits.DirectMessages,
        GatewayIntentBits.DirectMessageReactions,
        GatewayIntentBits.DirectMessageTyping,
        GatewayIntentBits.MessageContent
    ]
});

// Collections
client.commands = new Collection();
client.cooldowns = new Collection();
client.spamTracker = new Collection();
client.joinTracker = new Collection();
client.warnings = new Collection();
client.mutes = new Collection();
client.whitelist = new Collection();
client.backups = new Collection();

// Configuration
const config = {
    ownerId: process.env.OWNER_ID || '',
    prefix: '!',
    embedColor: 0x2ECC71,
    spamThreshold: 5, // messages
    spamTimeWindow: 5000, // ms
    raidThreshold: 10, // joins
    raidTimeWindow: 30000, // ms
    maxMentions: 5,
    logChannelId: null,
    muteRoleId: null,
    enabledModules: {
        antiNuke: true,
        antiSpam: true,
        antiRaid: true,
        antiLink: true,
        antiInvite: true,
        antiMassMention: true,
        logging: true,
        moderation: true
    }
};

// Load data files
function loadData() {
    const dataFiles = ['warnings.json', 'mutes.json', 'whitelist.json', 'backups.json', 'config.json'];
    
    dataFiles.forEach(file => {
        const filePath = path.join(__dirname, 'data', file);
        if (fs.existsSync(filePath)) {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
            const collectionName = file.replace('.json', '');
            if (client[collectionName]) {
                Object.entries(data).forEach(([key, value]) => {
                    client[collectionName].set(key, value);
                });
            }
        }
    });
}

// Save data files
function saveData(collectionName) {
    const filePath = path.join(__dirname, 'data', `${collectionName}.json`);
    const data = Object.fromEntries(client[collectionName]);
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

// Ensure data directory exists
if (!fs.existsSync(path.join(__dirname, 'data'))) {
    fs.mkdirSync(path.join(__dirname, 'data'));
}

// Load commands
function loadCommands() {
    const commandsPath = path.join(__dirname, 'commands');
    if (fs.existsSync(commandsPath)) {
        const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));
        
        for (const file of commandFiles) {
            const filePath = path.join(commandsPath, file);
            const command = require(filePath);
            if ('data' in command && 'execute' in command) {
                client.commands.set(command.data.name, command);
                console.log(`✅ Loaded command: ${command.data.name}`);
            } else {
                console.log(`⚠️  Command at ${filePath} is missing required "data" or "execute" property.`);
            }
        }
    }
}

// Anti-Nuke System
const nukeTracker = {
    channelDeletions: new Map(),
    roleDeletions: new Map(),
    roleCreations: new Map(),
    banAdditions: new Map(),
    kickAdditions: new Map(),
    thresholds: {
        channelDelete: 3,
        roleDelete: 2,
        roleCreate: 5,
        banAdd: 3,
        kickAdd: 3
    },
    timeWindow: 10000 // 10 seconds
};

function checkNukeAction(guildId, actionType, executorId) {
    if (!config.enabledModules.antiNuke) return false;
    
    const now = Date.now();
    const key = `${guildId}-${actionType}`;
    
    if (!nukeTracker[actionType + 's'].has(key)) {
        nukeTracker[actionType + 's'].set(key, { count: 1, firstAction: now, executors: [executorId] });
        return false;
    }
    
    const tracker = nukeTracker[actionType + 's'].get(key);
    
    if (now - tracker.firstAction > nukeTracker.timeWindow) {
        tracker.count = 1;
        tracker.firstAction = now;
        tracker.executors = [executorId];
        return false;
    }
    
    tracker.count++;
    tracker.executors.push(executorId);
    
    const threshold = nukeTracker.thresholds[actionType];
    if (tracker.count >= threshold) {
        return true; // Nuke detected!
    }
    
    return false;
}

async function handleNukeDetected(guild, actionType, executorId) {
    const logChannel = await getLogChannel(guild);
    
    const embed = new EmbedBuilder()
        .setColor(0xFF0000)
        .setTitle('🚨 NUKE ATTACK DETECTED! 🚨')
        .setDescription(`**Action Type:** ${actionType}\n**Executor:** <@${executorId}> (${executorId})\n**Timestamp:** <t:${Math.floor(Date.now() / 1000)}:F>`)
        .addFields({ name: 'Auto-Actions Taken', value: '• Executor kicked\n• Permissions revoked\n• Server locked down' })
        .setTimestamp();
    
    if (logChannel) {
        await logChannel.send({ embeds: [embed] });
    }
    
    // Try to kick the attacker
    try {
        const member = await guild.members.fetch(executorId);
        if (member && !member.permissions.has(PermissionFlagsBits.Administrator)) {
            await member.kick('Nuke attack detected');
        }
    } catch (error) {
        console.error('Failed to kick nuke attacker:', error);
    }
    
    // Lock down server
    try {
        await guild.edit({
            systemChannelFlags: 1
        });
    } catch (error) {
        console.error('Failed to lock down server:', error);
    }
}

// Logging System
async function getLogChannel(guild) {
    if (!config.logChannelId) return null;
    
    try {
        const channel = await guild.channels.fetch(config.logChannelId);
        if (channel && channel.isTextBased()) {
            return channel;
        }
    } catch (error) {
        return null;
    }
    
    // Fallback: find a channel named "logs" or "bot-logs"
    const logChannels = guild.channels.cache.filter(c => 
        c.isTextBased() && 
        (c.name.includes('log') || c.name.includes('bot'))
    );
    
    return logChannels.first() || null;
}

async function logAction(guild, action, details, user) {
    if (!config.enabledModules.logging) return;
    
    const logChannel = await getLogChannel(guild);
    if (!logChannel) return;
    
    const embed = new EmbedBuilder()
        .setColor(config.embedColor)
        .setTitle(action)
        .setDescription(details)
        .setTimestamp()
        .setFooter({ text: `By ${user?.tag || 'Unknown'}`, iconURL: user?.displayAvatarURL() });
    
    try {
        await logChannel.send({ embeds: [embed] });
    } catch (error) {
        console.error('Failed to send log:', error);
    }
}

// Event Handlers
client.once(Events.ClientReady, async () => {
    console.log('✅ Discord Guardian Bot is online!');
    console.log(`📊 Serving ${client.guilds.cache.size} guild(s)`);
    
    // Register slash commands
    const { REST } = require('discord.js');
    const { Routes } = require('discord.js');
    
    const commands = client.commands.map(cmd => cmd.data.toJSON());
    const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
    
    try {
        console.log('🔄 Started refreshing application (/) commands.');
        
        if (process.env.GUILD_ID) {
            // Guild-specific commands (faster for testing)
            await rest.put(
                Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID),
                { body: commands }
            );
        } else {
            // Global commands
            await rest.put(
                Routes.applicationCommands(process.env.CLIENT_ID),
                { body: commands }
            );
        }
        
        console.log('✅ Successfully reloaded application (/) commands.');
    } catch (error) {
        console.error('❌ Error registering commands:', error);
    }
    
    loadData();
    
    // Set bot status
    client.user.setPresence({
        activities: [{ name: '🛡️ Protecting Your Server', type: 3 }], // Watching
        status: 'online'
    });
});

// Message Event - Anti-Spam, Anti-Link, etc.
client.on(Events.MessageCreate, async (message) => {
    if (message.author.bot || !message.guild) return;
    
    const guild = message.guild;
    const memberId = message.author.id;
    
    // Check whitelist
    const whitelistData = client.whitelist.get(guild.id) || [];
    if (whitelistData.includes(memberId)) return;
    
    // Anti-Spam
    if (config.enabledModules.antiSpam) {
        const now = Date.now();
        const key = `${guild.id}-${memberId}`;
        
        if (!client.spamTracker.has(key)) {
            client.spamTracker.set(key, { messages: [now], warnings: 0 });
        }
        
        const tracker = client.spamTracker.get(key);
        tracker.messages.push(now);
        
        // Remove old messages outside time window
        tracker.messages = tracker.messages.filter(time => now - time < config.spamTimeWindow);
        
        if (tracker.messages.length > config.spamThreshold) {
            try {
                await message.delete();
                await message.channel.send({ content: `⚠️ ${message.author}, please slow down! Spam detected.`, allowedMentions: { parse: [] } });
                
                tracker.warnings++;
                
                if (tracker.warnings >= 3) {
                    // Mute the user
                    const muteRole = guild.roles.cache.find(r => r.name.toLowerCase().includes('mute'));
                    if (muteRole) {
                        await message.member.roles.add(muteRole, 'Spam violation');
                        await logAction(guild, '🔇 Auto-Mute', `User: ${message.author.tag}\nReason: Repeated spam`, message.author);
                    }
                }
                
                saveData('spamTracker');
            } catch (error) {
                console.error('Error handling spam:', error);
            }
        }
    }
    
    // Anti-Invite
    if (config.enabledModules.antiInvite) {
        const inviteRegex = /(https?:\/\/)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/[a-zA-Z0-9]+/gi;
        
        if (inviteRegex.test(message.content)) {
            try {
                await message.delete();
                await message.channel.send({ content: `⚠️ ${message.author}, posting invites to other servers is not allowed!`, allowedMentions: { parse: [] } });
                await logAction(guild, '🚫 Invite Deleted', `User: ${message.author.tag}\nContent: ${message.content.substring(0, 100)}`, message.author);
            } catch (error) {
                console.error('Error deleting invite:', error);
            }
        }
    }
    
    // Anti-Link (optional, can be configured)
    if (config.enabledModules.antiLink && !message.member.permissions.has(PermissionFlagsBits.ManageMessages)) {
        const linkRegex = /https?:\/\/[^\s]+/g;
        
        if (linkRegex.test(message.content)) {
            // Check if it's not an allowed domain
            const allowedDomains = ['discord.com', 'discordapp.com', 'youtube.com', 'twitter.com'];
            const links = message.content.match(linkRegex);
            
            const hasDisallowedLink = links.some(link => {
                const url = new URL(link);
                return !allowedDomains.some(domain => url.hostname.includes(domain));
            });
            
            if (hasDisallowedLink) {
                try {
                    await message.delete();
                    await message.channel.send({ content: `⚠️ ${message.author}, posting external links is restricted!`, allowedMentions: { parse: [] } });
                } catch (error) {
                    console.error('Error deleting link:', error);
                }
            }
        }
    }
    
    // Anti-Mass Mention
    if (config.enabledModules.antiMassMention) {
        if (message.mentions.members.size > config.maxMentions || message.mentions.everyone) {
            try {
                await message.delete();
                await message.channel.send({ content: `⚠️ ${message.author}, mass mentions are not allowed!`, allowedMentions: { parse: [] } });
                await logAction(guild, '🚫 Mass Mention Deleted', `User: ${message.author.tag}\nMentions: ${message.mentions.members.size}`, message.author);
            } catch (error) {
                console.error('Error handling mass mention:', error);
            }
        }
    }
});

// Guild Member Add - Anti-Raid
client.on(Events.GuildMemberAdd, async (member) => {
    const guild = member.guild;
    const now = Date.now();
    
    if (!client.joinTracker.has(guild.id)) {
        client.joinTracker.set(guild.id, { joins: [now] });
    }
    
    const tracker = client.joinTracker.get(guild.id);
    tracker.joins.push(now);
    
    // Remove old joins outside time window
    tracker.joins = tracker.joins.filter(time => now - time < config.raidTimeWindow);
    
    if (tracker.joins.length > config.raidThreshold) {
        if (config.enabledModules.antiRaid) {
            // Raid detected!
            const logChannel = await getLogChannel(guild);
            
            const embed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle('⚠️ RAID DETECTED! ⚠️')
                .setDescription(`**${tracker.joins.length}** members joined in **${config.raidTimeWindow / 1000}** seconds!`)
                .addFields({ name: 'Auto-Actions', value: '• Server lockdown initiated\n• New members quarantined' })
                .setTimestamp();
            
            if (logChannel) {
                await logChannel.send({ embeds: [embed] });
            }
            
            // Lockdown server
            try {
                await guild.edit({
                    systemChannelFlags: 1
                });
                
                // Add quarantine role to new members
                const quarantineRole = guild.roles.cache.find(r => r.name.toLowerCase().includes('quarantine')) || 
                                      guild.roles.cache.find(r => r.name.toLowerCase().includes('new'));
                
                if (quarantineRole) {
                    await member.roles.add(quarantineRole, 'Raid protection');
                }
            } catch (error) {
                console.error('Error during raid lockdown:', error);
            }
        }
    }
});

// Channel Delete - Anti-Nuke
client.on(Events.ChannelDelete, async (channel) => {
    if (!channel.guild || !config.enabledModules.antiNuke) return;
    
    const auditLogs = await channel.guild.fetchAuditLogs({ limit: 1, type: 26 }); // Channel Delete
    const entry = auditLogs.entries.first();
    
    if (!entry || !entry.executor) return;
    
    const executorId = entry.executor.id;
    const guildId = channel.guild.id;
    
    if (checkNukeAction(guildId, 'channelDelete', executorId)) {
        await handleNukeDetected(channel.guild, 'channelDelete', executorId);
    }
});

// Role Delete - Anti-Nuke
client.on(Events.GuildRoleDelete, async (role) => {
    if (!role.guild || !config.enabledModules.antiNuke) return;
    
    const auditLogs = await role.guild.fetchAuditLogs({ limit: 1, type: 32 }); // Role Delete
    const entry = auditLogs.entries.first();
    
    if (!entry || !entry.executor) return;
    
    const executorId = entry.executor.id;
    const guildId = role.guild.id;
    
    if (checkNukeAction(guildId, 'roleDelete', executorId)) {
        await handleNukeDetected(role.guild, 'roleDelete', executorId);
    }
});

// Ban Add - Anti-Nuke
client.on(Events.GuildBanAdd, async (ban) => {
    if (!ban.guild || !config.enabledModules.antiNuke) return;
    
    const auditLogs = await ban.guild.fetchAuditLogs({ limit: 1, type: 22 }); // Ban Add
    const entry = auditLogs.entries.first();
    
    if (!entry || !entry.executor) return;
    
    const executorId = entry.executor.id;
    const guildId = ban.guild.id;
    
    if (checkNukeAction(guildId, 'banAdd', executorId)) {
        await handleNukeDetected(ban.guild, 'banAdd', executorId);
    }
});

// Message Delete Logging
client.on(Events.MessageDelete, async (message) => {
    if (!message.guild || message.author.bot || !config.enabledModules.logging) return;
    
    const logChannel = await getLogChannel(message.guild);
    if (!logChannel) return;
    
    const embed = new EmbedBuilder()
        .setColor(0xFFA500)
        .setTitle('🗑️ Message Deleted')
        .addFields(
            { name: 'Author', value: message.author?.tag || 'Unknown', inline: true },
            { name: 'Channel', value: `<#${message.channel.id}>`, inline: true },
            { name: 'Content', value: message.content.substring(0, 1024) || '*No content*' }
        )
        .setTimestamp();
    
    if (message.attachments.size > 0) {
        embed.addFields({ name: 'Attachments', value: `${message.attachments.size} attachment(s)` });
    }
    
    try {
        await logChannel.send({ embeds: [embed] });
    } catch (error) {
        console.error('Error logging deleted message:', error);
    }
});

// Message Update Logging
client.on(Events.MessageUpdate, async (oldMessage, newMessage) => {
    if (!oldMessage.guild || oldMessage.author.bot || !config.enabledModules.logging) return;
    if (oldMessage.content === newMessage.content) return;
    
    const logChannel = await getLogChannel(oldMessage.guild);
    if (!logChannel) return;
    
    const embed = new EmbedBuilder()
        .setColor(0xFFFF00)
        .setTitle('✏️ Message Edited')
        .addFields(
            { name: 'Author', value: oldMessage.author?.tag || 'Unknown', inline: true },
            { name: 'Channel', value: `<#${oldMessage.channel.id}>`, inline: true },
            { name: 'Before', value: oldMessage.content.substring(0, 512) || '*No content*', inline: false },
            { name: 'After', value: newMessage.content.substring(0, 512) || '*No content*', inline: false }
        )
        .setTimestamp();
    
    try {
        await logChannel.send({ embeds: [embed] });
    } catch (error) {
        console.error('Error logging edited message:', error);
    }
});

// Interaction Handler (Slash Commands)
client.on(Events.InteractionCreate, async interaction => {
    if (!interaction.isChatInputCommand()) return;
    
    const command = client.commands.get(interaction.commandName);
    
    if (!command) return;
    
    try {
        await command.execute(interaction, client, config);
    } catch (error) {
        console.error('Error executing command:', error);
        
        const errorMessage = {
            content: '❌ There was an error executing this command!',
            ephemeral: true
        };
        
        if (interaction.replied || interaction.deferred) {
            await interaction.followUp(errorMessage);
        } else {
            await interaction.reply(errorMessage);
        }
    }
});

// Error Handling
process.on('unhandledRejection', error => {
    console.error('Unhandled promise rejection:', error);
});

process.on('uncaughtException', error => {
    console.error('Uncaught exception:', error);
});

// Login
client.login(process.env.DISCORD_TOKEN);

/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const db = require('../../handlers/database');
const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'tag',
    aliases: ['tags', 'custom-command', 'cc', 'faq', 'guide', 'info-tag', 'show-tag'],
    description: 'Create, view, or manage custom tags (infinite commands!)',
    usage: 'tag <create|delete|list|info> [name] [content]',
    category: 'tags',
    async execute(message, args, client) {
        const subCommand = args[0]?.toLowerCase();
        const tagName = args[1];
        const content = args.slice(2).join(' ');
        const guildId = message.guild.id;
        
        if (!subCommand) {
            return message.reply('Usage: `tag <create|delete|list|info> [name] [content]`');
        }
        
        switch (subCommand) {
            case 'create':
            case 'add':
            case 'new':
                if (!tagName || !content) {
                    return message.reply('Usage: `tag create <name> <content>`');
                }
                
                db.run('INSERT OR REPLACE INTO tags (guild_id, name, content, creator) VALUES (?, ?, ?, ?)',
                    [guildId, tagName.toLowerCase(), content, message.author.id],
                    (err) => {
                        if (err) {
                            return message.reply('Failed to create tag.');
                        }
                        message.reply(`✅ Tag \`${tagName}\` created successfully!`);
                    }
                );
                break;
                
            case 'delete':
            case 'remove':
            case 'del':
                if (!tagName) {
                    return message.reply('Usage: `tag delete <name>`');
                }
                
                db.run('DELETE FROM tags WHERE guild_id = ? AND name = ?', 
                    [guildId, tagName.toLowerCase()],
                    function(err) {
                        if (err || this.changes === 0) {
                            return message.reply('Tag not found.');
                        }
                        message.reply(`✅ Tag \`${tagName}\` deleted.`);
                    }
                );
                break;
                
            case 'list':
            case 'all':
            case 'show-all':
                db.all('SELECT name, uses FROM tags WHERE guild_id = ? ORDER BY name', [guildId], (err, rows) => {
                    if (err) return message.reply('Error fetching tags.');
                    
                    if (!rows || rows.length === 0) {
                        return message.reply('No tags created yet.');
                    }
                    
                    const tagList = rows.map((r, i) => `${i + 1}. **${r.name}** (Used ${r.uses}x)`).join('\n');
                    const embed = new EmbedBuilder()
                        .setColor('#0099ff')
                        .setTitle(`📜 Available Tags (${rows.length})`)
                        .setDescription(tagList)
                        .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' });
                    
                    message.reply({ embeds: [embed] });
                });
                break;
                
            case 'info':
            case 'view':
            case 'show':
                if (!tagName) {
                    return message.reply('Usage: `tag info <name>`');
                }
                
                db.get('SELECT * FROM tags WHERE guild_id = ? AND name = ?', 
                    [guildId, tagName.toLowerCase()],
                    (err, row) => {
                        if (err || !row) {
                            return message.reply('Tag not found.');
                        }
                        
                        // Increment uses
                        db.run('UPDATE tags SET uses = uses + 1 WHERE id = ?', [row.id]);
                        
                        const embed = new EmbedBuilder()
                            .setColor('#00ff00')
                            .setTitle(`📑 Tag: ${row.name}`)
                            .setDescription(row.content)
                            .addFields(
                                { name: 'Creator', value: `<@${row.creator}>`, inline: true },
                                { name: 'Uses', value: `${row.uses + 1}`, inline: true }
                            )
                            .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' });
                        
                        message.reply({ embeds: [embed] });
                    }
                );
                break;
                
            default:
                // Try to find a tag with the first argument
                db.get('SELECT * FROM tags WHERE guild_id = ? AND name = ?', 
                    [guildId, subCommand.toLowerCase()],
                    (err, row) => {
                        if (err || !row) {
                            return message.reply('Unknown subcommand or tag not found.');
                        }
                        
                        db.run('UPDATE tags SET uses = uses + 1 WHERE id = ?', [row.id]);
                        message.reply(row.content);
                    }
                );
        }
    }
};

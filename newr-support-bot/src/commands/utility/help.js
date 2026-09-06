/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'help',
    aliases: ['commands', 'support', 'info', 'guide', 'manual', 'how-to', 'h'],
    description: 'Show all available commands and support info',
    usage: 'help [command]',
    category: 'utility',
    async execute(message, args, client) {
        const prefix = '!'; // Default prefix
        const categories = {
            'ticket': '🎫 Ticket System',
            'support': '🤝 Support & Reports',
            'moderation': '🔨 Moderation',
            'tags': '🏷️ Custom Tags (Infinite Commands)',
            'info': 'ℹ️ Information',
            'config': '⚙️ Configuration',
            'utility': '🛠️ Utilities'
        };
        
        if (args[0]) {
            const command = client.commands.get(args[0].toLowerCase()) || 
                           Array.from(client.commands.values()).find(c => c.aliases?.includes(args[0].toLowerCase()));
            
            if (!command) {
                return message.reply('Command not found.');
            }
            
            const embed = new EmbedBuilder()
                .setColor('#0099ff')
                .setTitle(`📖 Help: ${command.name}`)
                .setDescription(command.description)
                .addFields(
                    { name: 'Usage', value: `\`${prefix}${command.usage}\``, inline: false },
                    { name: 'Aliases', value: command.aliases?.join(', ') || 'None', inline: true },
                    { name: 'Category', value: categories[command.category] || command.category, inline: true }
                )
                .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' });
            
            return message.reply({ embeds: [embed] });
        }
        
        const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle('🛡️ NEWROPLY Ultimate Support Bot')
            .setDescription('**The most complete Discord support bot with 999999+ features!**\n\nDeveloped by **NEWR LABS**.\n\nUse `!help <command>` for detailed info.')
            .setThumbnail(message.guild.iconURL({ dynamic: true }))
            .setTimestamp();
        
        let fields = [];
        for (const [cat, name] of Object.entries(categories)) {
            const cmds = Array.from(client.commands.values())
                .filter(c => c.category === cat && !c.aliases?.includes(c.name))
                .slice(0, 10)
                .map(c => `\`${c.name}\``)
                .join(', ');
            
            if (cmds) {
                fields.push({ name: `${name} (${Array.from(client.commands.values()).filter(c => c.category === cat).length}+ commands)`, value: cmds || 'No commands', inline: false });
            }
        }
        
        embed.addFields(fields);
        embed.setFooter({ text: `© NEWROPLY - Developed by NEWR LABS | Total Commands: ${client.commands.size}` });
        
        message.reply({ embeds: [embed] });
    }
};

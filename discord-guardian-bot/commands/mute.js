const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('mute')
        .setDescription('Mute a user temporarily')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to mute')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('duration')
                .setDescription('Duration (e.g., 1h, 30m, 7d, 1w)')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Reason for the mute')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user');
        const durationStr = interaction.options.getString('duration');
        const reason = interaction.options.getString('reason') || 'No reason provided';
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to mute users!', 
                ephemeral: true 
            });
        }
        
        const member = await interaction.guild.members.fetch(user.id).catch(() => null);
        
        if (!member) {
            return interaction.reply({ 
                content: '❌ User not found in this server!', 
                ephemeral: true 
            });
        }
        
        if (member.id === interaction.user.id) {
            return interaction.reply({ 
                content: '❌ You cannot mute yourself!', 
                ephemeral: true 
            });
        }
        
        if (member.roles.highest.position >= interaction.member.roles.highest.position) {
            return interaction.reply({ 
                content: '❌ You cannot mute someone with a higher or equal role!', 
                ephemeral: true 
            });
        }
        
        if (!member.moderatable) {
            return interaction.reply({ 
                content: '❌ I cannot mute this user! They might have higher permissions.', 
                ephemeral: true 
            });
        }
        
        // Parse duration
        const duration = parseDuration(durationStr);
        
        if (!duration || duration > 2419200000) { // Max 28 days
            return interaction.reply({ 
                content: '❌ Invalid duration! Use format like: 1h, 30m, 7d, 1w (max 28 days)', 
                ephemeral: true 
            });
        }
        
        try {
            await member.timeout(duration, `${reason} | Muted by ${interaction.user.tag}`);
            
            const embed = new EmbedBuilder()
                .setColor(0xFFA500)
                .setTitle('🔇 User Muted')
                .addFields(
                    { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                    { name: 'Moderator', value: `${interaction.user.tag}`, inline: true },
                    { name: 'Duration', value: durationStr, inline: true },
                    { name: 'Reason', value: reason, inline: false }
                )
                .setTimestamp()
                .setFooter({ text: `ID: ${user.id}` });
            
            await interaction.reply({ embeds: [embed] });
            
        } catch (error) {
            console.error('Error muting user:', error);
            await interaction.reply({ 
                content: '❌ Failed to mute the user! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};

// Helper function to parse duration string to milliseconds
function parseDuration(str) {
    const match = str.match(/^(\d+)([smhdw])$/i);
    if (!match) return null;
    
    const value = parseInt(match[1]);
    const unit = match[2].toLowerCase();
    
    const multipliers = {
        s: 1000,
        m: 60000,
        h: 3600000,
        d: 86400000,
        w: 604800000
    };
    
    return value * multipliers[unit];
}

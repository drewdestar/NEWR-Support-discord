const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('lock')
        .setDescription('Lock a channel to prevent members from sending messages')
        .addChannelOption(option =>
            option.setName('channel')
                .setDescription('The channel to lock (defaults to current channel)')
                .setRequired(false)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ManageChannels),
    
    async execute(interaction, client, config) {
        const channel = interaction.options.getChannel('channel') || interaction.channel;
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ManageChannels)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to manage channels!', 
                ephemeral: true 
            });
        }
        
        if (!channel.isTextBased()) {
            return interaction.reply({ 
                content: '❌ You can only lock text channels!', 
                ephemeral: true 
            });
        }
        
        try {
            // Get the @everyone role
            const everyoneRole = interaction.guild.roles.everyone;
            
            // Set permissions to deny SEND_MESSAGES
            await channel.permissionOverwrites.edit(everyoneRole, {
                SendMessages: false
            }, `Channel locked by ${interaction.user.tag}`);
            
            const embed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle('🔒 Channel Locked')
                .setDescription(`**${channel.name}** has been locked!\nMembers can no longer send messages in this channel.`)
                .addFields({ name: 'Moderator', value: `${interaction.user.tag}`, inline: true })
                .setTimestamp();
            
            await interaction.reply({ embeds: [embed] });
            
        } catch (error) {
            console.error('Error locking channel:', error);
            await interaction.reply({ 
                content: '❌ Failed to lock the channel! Make sure I have the necessary permissions.', 
                ephemeral: true 
            });
        }
    }
};
